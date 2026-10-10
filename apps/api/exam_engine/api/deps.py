"""Dependencias comunes: sesión de docente por cookie, CSRF y contexto de universidad."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import db, models
from ..services.admin_auth import AdminPrincipal, resolve_session

ADMIN_COOKIE = "mev_admin"
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "mev"


def client_ip(request: Request) -> str:
    # App Service antepone la IP real en X-Forwarded-For; se toma el primer valor.
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip().split(":")[0] if fwd else (request.client.host if request.client else "?"))[:64]


def require_csrf(request: Request) -> None:
    """Para métodos que modifican estado se exige una cabecera propia (obliga a preflight CORS, que no se
    permite para otros orígenes) además de SameSite=Strict en la cookie."""
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise HTTPException(status_code=403, detail="Solicitud no permitida.")


def current_admin(request: Request, _: None = Depends(require_csrf)) -> AdminPrincipal:
    principal = resolve_session(request.cookies.get(ADMIN_COOKIE))
    if principal is None:
        raise HTTPException(status_code=401, detail="Inicia sesión.")
    return principal


def active_admin(principal: AdminPrincipal = Depends(current_admin)) -> AdminPrincipal:
    """Como current_admin, pero exige haber cambiado una contraseña temporal."""
    if principal.must_change_password:
        raise HTTPException(status_code=403, detail="Debes cambiar tu contraseña temporal antes de continuar.")
    return principal


@contextmanager
def admin_scope(principal: AdminPrincipal) -> Iterator[Session]:
    """Transacción con el contexto RLS del docente (platform_admin ve todas las universidades)."""
    if principal.role == "platform_admin":
        with db.tenant_session(None, platform_admin=True) as s:
            yield s
    else:
        with db.tenant_session(uuid.UUID(principal.university_id or "")) as s:
            yield s


def load_course(s: Session, principal: AdminPrincipal, course_id: uuid.UUID) -> models.Course:
    course = s.get(models.Course, course_id)  # RLS ya oculta materias de otras universidades
    if course is None:
        raise HTTPException(status_code=404, detail="Materia no encontrada.")
    if principal.role == "teacher":
        allowed = s.scalar(
            select(models.AdministratorCourse).where(
                models.AdministratorCourse.administrator_id == uuid.UUID(principal.id),
                models.AdministratorCourse.course_id == course_id,
            )
        )
        if allowed is None:
            raise HTTPException(status_code=404, detail="Materia no encontrada.")
    return course
