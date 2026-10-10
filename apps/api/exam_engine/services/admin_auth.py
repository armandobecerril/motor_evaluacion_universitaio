"""Autenticación de docentes: usuario + contraseña (Argon2id), sesiones opacas y bloqueo por intentos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .. import db, models
from ..config import get_settings
from ..security import hash_password, new_token, password_problems, token_hash, verify_password

IP_WINDOW_MINUTES = 15
IP_MAX_ATTEMPTS = 30


@dataclass(frozen=True)
class AdminPrincipal:
    id: str
    username: str
    display_name: str
    role: str
    university_id: str | None
    must_change_password: bool


class LoginError(Exception):
    def __init__(self, message: str, status: int = 401) -> None:
        super().__init__(message)
        self.status = status


def _principal(a: models.Administrator) -> AdminPrincipal:
    return AdminPrincipal(
        id=str(a.id),
        username=a.username,
        display_name=a.display_name,
        role=a.role,
        university_id=str(a.university_id) if a.university_id else None,
        must_change_password=a.must_change_password,
    )


def throttle_hit(s: Session, key: str, window_minutes: int, limit: int) -> bool:
    """Incrementa el contador de la ventana; devuelve True si se excedió el límite."""
    now = datetime.now(UTC)
    start = now.replace(second=0, microsecond=0) - timedelta(minutes=now.minute % window_minutes)
    stmt = (
        insert(models.AccessThrottle)
        .values(key=key, window_start=start, attempts=1)
        .on_conflict_do_update(
            index_elements=["key", "window_start"],
            set_={"attempts": models.AccessThrottle.attempts + 1},
        )
        .returning(models.AccessThrottle.attempts)
    )
    return s.execute(stmt).scalar_one() > limit


def login(username: str, password: str, client_ip: str) -> tuple[AdminPrincipal, str]:
    """Las fallas se registran (contador, bloqueo, auditoría) y se confirman ANTES de responder el error."""
    settings = get_settings()
    now = datetime.now(UTC)
    username = username.strip().lower()
    failure: LoginError | None = None
    result: tuple[AdminPrincipal, str] | None = None
    with db.tenant_session(None, platform_admin=True) as s:
        if throttle_hit(s, f"admin-login:ip:{client_ip}", IP_WINDOW_MINUTES, IP_MAX_ATTEMPTS):
            failure = LoginError("Demasiados intentos. Espera unos minutos.", 429)
        else:
            admin = s.scalar(select(models.Administrator).where(models.Administrator.username == username))
            ok = verify_password(admin.password_hash if admin else None, password)  # tiempo constante
            if admin is None or not admin.active:
                failure = LoginError("Usuario o contraseña incorrectos.")
            elif admin.locked_until and admin.locked_until > now:
                failure = LoginError("Cuenta bloqueada temporalmente por intentos fallidos.", 423)
            elif not ok:
                admin.failed_logins += 1
                if admin.failed_logins >= settings.admin_max_failed_logins:
                    admin.locked_until = now + timedelta(minutes=settings.admin_lockout_minutes)
                    admin.failed_logins = 0
                s.add(
                    models.AuditEvent(
                        university_id=admin.university_id,
                        actor_type="admin",
                        actor_id=admin.username,
                        event_type="admin.login_failed",
                        event_metadata={"ip": client_ip},
                    )
                )
                failure = LoginError("Usuario o contraseña incorrectos.")
            else:
                admin.failed_logins = 0
                admin.locked_until = None
                admin.last_login_at = now
                token = new_token()
                s.add(
                    models.AdminSession(
                        administrator_id=admin.id,
                        token_hash=token_hash(token),
                        expires_at=now + timedelta(hours=settings.admin_session_hours),
                    )
                )
                s.add(
                    models.AuditEvent(
                        university_id=admin.university_id,
                        actor_type="admin",
                        actor_id=admin.username,
                        event_type="admin.login",
                        event_metadata={"ip": client_ip},
                    )
                )
                result = (_principal(admin), token)
    if failure is not None:
        raise failure
    assert result is not None
    return result


def resolve_session(token: str | None) -> AdminPrincipal | None:
    if not token:
        return None
    now = datetime.now(UTC)
    with db.tenant_session(None, platform_admin=True) as s:
        row = s.execute(
            select(models.Administrator)
            .join(models.AdminSession, models.AdminSession.administrator_id == models.Administrator.id)
            .where(
                models.AdminSession.token_hash == token_hash(token),
                models.AdminSession.revoked_at.is_(None),
                models.AdminSession.expires_at > now,
                models.Administrator.active.is_(True),
            )
        ).scalar_one_or_none()
        return _principal(row) if row else None


def logout(token: str | None) -> None:
    if not token:
        return
    with db.tenant_session(None, platform_admin=True) as s:
        s.execute(
            update(models.AdminSession)
            .where(models.AdminSession.token_hash == token_hash(token), models.AdminSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )


def change_password(principal: AdminPrincipal, current: str, new: str) -> list[str]:
    problems = password_problems(new, principal.username)
    if problems:
        return problems
    with db.tenant_session(None, platform_admin=True) as s:
        admin = s.get(models.Administrator, principal.id)
        if admin is None or not verify_password(admin.password_hash, current):
            return ["La contraseña actual no es correcta."]
        if verify_password(admin.password_hash, new):
            return ["La nueva contraseña debe ser distinta de la actual."]
        admin.password_hash = hash_password(new)
        admin.must_change_password = False
        # Revoca las demás sesiones abiertas.
        s.execute(
            update(models.AdminSession)
            .where(models.AdminSession.administrator_id == admin.id, models.AdminSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        s.add(
            models.AuditEvent(
                university_id=admin.university_id,
                actor_type="admin",
                actor_id=admin.username,
                event_type="admin.password_changed",
                event_metadata={},
            )
        )
    return []


def create_admin(
    *,
    username: str,
    password: str,
    display_name: str,
    role: str,
    university_code: str | None,
    temporary: bool,
) -> str:
    """Alta o restablecimiento de un docente/admin (CLI). ``temporary`` obliga a cambiarla al entrar."""
    username = username.strip().lower()
    with db.tenant_session(None, platform_admin=True) as s:
        uni_id = None
        if university_code:
            uni = s.scalar(select(models.University).where(models.University.code == university_code))
            if uni is None:
                raise ValueError(f"Universidad '{university_code}' no existe.")
            uni_id = uni.id
        admin = s.scalar(select(models.Administrator).where(models.Administrator.username == username))
        if admin is None:
            admin = models.Administrator(username=username, display_name=display_name, role=role, university_id=uni_id)
            s.add(admin)
            action = "creado"
        else:
            action = "actualizado"
        admin.password_hash = hash_password(password)
        admin.must_change_password = temporary
        admin.failed_logins = 0
        admin.locked_until = None
        admin.active = True
        s.flush()
        s.add(
            models.AuditEvent(
                university_id=uni_id,
                actor_type="system",
                actor_id="cli",
                event_type=f"admin.{action}",
                event_metadata={"username": username, "role": role},
            )
        )
        return f"{action}: {username} ({role})"
