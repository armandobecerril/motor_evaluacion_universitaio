"""Flujo del alumno: ingreso, pregunta actual, respuesta idempotente y cierre.

Reglas:
- El reloj es el del servidor (``clock.now``). El deadline de cada pregunta se fija al servirla.
- Una respuesta tardía (después de deadline + tolerancia) se registra como ``expired`` y vale 0.
- Cada operación bloquea la fila del intento (``SELECT … FOR UPDATE``) → sin carreras entre pestañas.
- Nunca se devuelve qué opción es correcta ni la justificación.
"""

from __future__ import annotations

import re
import secrets
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import db, models
from ..config import get_settings
from ..security import access_code_lookup, token_hash
from . import clock, scoring
from .admin_auth import throttle_hit
from .exams import audit
from .selection import PoolItem, SelectionError
from .selection import select as select_questions

MATRICULA_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
LABELS = ("A", "B", "C", "D")


class StudentError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _fold(text: str) -> str:
    norm = unicodedata.normalize("NFKD", " ".join(text.split()).lower())
    return "".join(c for c in norm if not unicodedata.combining(c))


def clean_name(full_name: str) -> str:
    name = " ".join(full_name.split())
    if not (5 <= len(name) <= 200) or len(name.split()) < 2:
        raise StudentError("Escribe tu nombre completo (nombre y apellidos).", 422)
    return name


def clean_matricula(matricula: str) -> str:
    m = matricula.strip().upper()
    if not MATRICULA_RE.match(m):
        raise StudentError("Matrícula no válida: usa letras, números, punto, guion o guion bajo.", 422)
    return m


# --------------------------------------------------------------------- ingreso ---


@dataclass
class StartResult:
    token: str
    attempt_id: uuid.UUID
    resumed: bool
    window_deadline_at: Any


def start(access_code: str, full_name: str, matricula: str, client_ip: str) -> StartResult:
    name = clean_name(full_name)
    mat = clean_matricula(matricula)
    pepper = get_settings().access_code_pepper.get_secret_value()
    lookup = access_code_lookup(access_code, pepper)

    # 1) Resolver examen por código (antes de conocer la universidad) + límite por IP.
    with db.tenant_session(None, platform_admin=True) as s:
        # Un salón puede compartir IP (NAT): límite holgado por IP.
        limited = throttle_hit(s, f"student-start:ip:{client_ip}", 15, 300)
        row = (
            None
            if limited
            else s.execute(
                select(models.Exam.id, models.Exam.university_id).where(models.Exam.access_code_lookup == lookup)
            ).first()
        )
    if limited:
        raise StudentError("Demasiados intentos desde esta red. Espera unos minutos.", 429)
    if row is None:
        raise StudentError("Código de acceso no válido.", 404)
    exam_id, university_id = row

    for _ in range(2):  # un reintento si otro ingreso simultáneo creó el intento primero
        try:
            with db.tenant_session(university_id) as s:
                return _start_in_tenant(s, exam_id, name, mat, client_ip)
        except IntegrityError:
            continue
    raise StudentError("No fue posible iniciar; intenta de nuevo.", 409)


def _start_in_tenant(s: Session, exam_id: uuid.UUID, name: str, mat: str, ip: str) -> StartResult:
    now = clock.now()
    exam = s.get(models.Exam, exam_id, with_for_update={"read": True})
    if exam is None or exam.status != "published":
        raise StudentError("Este examen no está disponible.", 403)
    if now < exam.starts_at:
        tz = ZoneInfo(str(exam.config.get("timezone", "America/Mexico_City")))
        raise StudentError(f"El examen abre el {exam.starts_at.astimezone(tz):%d/%m/%Y a las %H:%M}.", 403)
    if now > exam.ends_at:
        raise StudentError("El periodo del examen ya terminó.", 403)

    s.execute(
        insert(models.Student)
        .values(university_id=exam.university_id, matricula=mat, full_name=name)
        .on_conflict_do_nothing(index_elements=["university_id", "matricula"])
    )
    student = s.scalar(
        select(models.Student).where(
            models.Student.university_id == exam.university_id, models.Student.matricula == mat
        )
    )
    assert student is not None
    attempt = s.scalar(
        select(models.ExamAttempt)
        .where(models.ExamAttempt.exam_id == exam.id, models.ExamAttempt.student_id == student.id)
        .order_by(models.ExamAttempt.attempt_number.desc())
        .with_for_update()
    )
    token = secrets.token_urlsafe(32)
    if attempt is not None:
        finalize_if_expired(s, attempt)
        if attempt.status != "in_progress":
            raise StudentError("Esta matrícula ya presentó el examen. Si es un error, consulta a tu docente.", 409)
        if _fold(attempt.full_name_entered) != _fold(name):
            audit(s, exam.university_id, "student", "attempt.resume_name_mismatch", attempt.id, ip=ip)
            raise StudentError(
                "Esta matrícula tiene un examen en curso con otro nombre. Escribe tu nombre exactamente igual.", 409
            )
        attempt.token_hash = token_hash(token)
        attempt.row_version += 1
        audit(s, exam.university_id, "student", "attempt.resumed", attempt.id, ip=ip)
        return StartResult(token, attempt.id, True, attempt.window_deadline_at)

    cfg = dict(exam.config)
    pool_rows = s.execute(
        select(models.QuestionBank.id, models.QuestionBank.module_number, models.QuestionBank.conceptual_group)
        .join(models.ExamQuestion, models.ExamQuestion.question_id == models.QuestionBank.id)
        .where(models.ExamQuestion.exam_id == exam.id)
    ).all()
    try:
        chosen = select_questions(
            [PoolItem(qid, m, g) for qid, m, g in pool_rows],
            cfg["modules"],
            int(cfg["per_module_quota"]),
            int(cfg["max_variants_per_group"]),
        )
    except SelectionError as exc:
        raise StudentError("El examen no tiene suficientes preguntas aprobadas. Avisa a tu docente.", 503) from exc
    window = min(now + timedelta(minutes=int(cfg["window_minutes"])), exam.ends_at)
    attempt = models.ExamAttempt(
        university_id=exam.university_id,
        exam_id=exam.id,
        student_id=student.id,
        attempt_number=1,
        full_name_entered=name,
        status="in_progress",
        started_at=now,
        window_deadline_at=window,
        current_ordinal=1,
        seed=secrets.token_hex(16),
        config_snapshot=cfg,
        token_hash=token_hash(token),
    )
    s.add(attempt)
    s.flush()
    s.add_all(
        models.AttemptQuestion(
            attempt_id=attempt.id,
            ordinal=i,
            university_id=exam.university_id,
            question_id=c.question_id,
            module_number=c.module_number,
            options_order=list(c.options_order),
            state="pending",
        )
        for i, c in enumerate(chosen, start=1)
    )
    audit(s, exam.university_id, "student", "attempt.started", attempt.id, ip=ip, questions=len(chosen))
    s.flush()
    return StartResult(token, attempt.id, False, window)


# ------------------------------------------------------------ sesión de intento ---


def _resolve(token: str | None) -> tuple[uuid.UUID, uuid.UUID]:
    if not token:
        raise StudentError("No hay un examen en curso en este navegador.", 401)
    with db.tenant_session(None, platform_admin=True) as s:
        row = s.execute(
            select(models.ExamAttempt.id, models.ExamAttempt.university_id).where(
                models.ExamAttempt.token_hash == token_hash(token)
            )
        ).first()
    if row is None:
        raise StudentError("Tu sesión de examen no es válida o fue reemplazada por otro ingreso.", 401)
    return row[0], row[1]


def _locked_attempt(s: Session, attempt_id: uuid.UUID) -> models.ExamAttempt:
    a = s.get(models.ExamAttempt, attempt_id, with_for_update=True)
    assert a is not None
    return a


def finalize(s: Session, attempt: models.ExamAttempt, *, reason: str) -> None:
    if attempt.status != "in_progress":
        return
    outcomes = list(
        s.scalars(select(models.AttemptAnswer.outcome).where(models.AttemptAnswer.attempt_id == attempt.id))
    )
    cfg = attempt.config_snapshot
    total = int(cfg["questions_per_attempt"])
    sc = scoring.compute(outcomes, total, cfg["scoring"])
    s.add(
        models.AttemptResult(
            attempt_id=attempt.id,
            university_id=attempt.university_id,
            total=sc.total,
            correct=sc.correct,
            wrong=sc.wrong,
            omitted=sc.omitted,
            expired=sc.expired,
            raw_score=sc.raw,
            grade=sc.grade,
        )
    )
    attempt.status = "finished" if reason == "completed" else "expired"
    attempt.finished_at = clock.now()
    attempt.row_version += 1
    audit(
        s,
        attempt.university_id,
        "system",
        "attempt.finished",
        attempt.id,
        reason=reason,
        grade=sc.grade_display,
        correct=sc.correct,
        wrong=sc.wrong,
    )


def finalize_if_expired(s: Session, attempt: models.ExamAttempt) -> None:
    if attempt.status == "in_progress" and clock.now() > attempt.window_deadline_at:
        finalize(s, attempt, reason="window_expired")


def _tolerance(attempt: models.ExamAttempt) -> timedelta:
    return timedelta(milliseconds=int(attempt.config_snapshot.get("network_tolerance_ms", 0)))


def _advance(s: Session, attempt: models.ExamAttempt) -> dict[str, Any]:
    """Sirve la pregunta actual (fija su deadline) o expira la vencida y avanza."""
    cfg = attempt.config_snapshot
    total = int(cfg["questions_per_attempt"])
    secs = int(cfg["seconds_per_question"])
    while True:
        finalize_if_expired(s, attempt)
        if attempt.status != "in_progress":
            return _finished_payload(s, attempt)
        if attempt.current_ordinal > total:
            finalize(s, attempt, reason="completed")
            return _finished_payload(s, attempt)
        now = clock.now()
        aq = s.get(models.AttemptQuestion, (attempt.id, attempt.current_ordinal), with_for_update=True)
        assert aq is not None
        if aq.served_at is None:
            aq.served_at = now
            aq.deadline_at = min(now + timedelta(seconds=secs), attempt.window_deadline_at)
            aq.state = "served"
            s.flush()
        elif now > aq.deadline_at + _tolerance(attempt):
            _record(s, attempt, aq, outcome="expired", option_id=None, key=f"auto-expired-{aq.ordinal}")
            continue
        return _question_payload(s, attempt, aq, now)


def _record(s: Session, attempt, aq, *, outcome: str, option_id, key: str) -> None:  # type: ignore[no-untyped-def]
    s.add(
        models.AttemptAnswer(
            university_id=attempt.university_id,
            attempt_id=attempt.id,
            ordinal=aq.ordinal,
            selected_option_id=option_id,
            outcome=outcome,
            idempotency_key=key[:64],
            received_at=clock.now(),
        )
    )
    aq.state = {"correct": "answered", "wrong": "answered"}.get(outcome, outcome)
    attempt.current_ordinal = aq.ordinal + 1
    attempt.row_version += 1
    s.flush()


def _question_payload(s: Session, attempt, aq, now) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    q = s.get(models.QuestionBank, aq.question_id)
    opts = {
        o.option_code: o.text
        for o in s.scalars(select(models.QuestionOption).where(models.QuestionOption.question_id == aq.question_id))
    }
    cfg = attempt.config_snapshot
    return {
        "status": "in_progress",
        "ordinal": aq.ordinal,
        "total": int(cfg["questions_per_attempt"]),
        "module": aq.module_number,
        "stem": q.stem,
        "options": [{"index": i, "label": LABELS[i], "text": opts[code]} for i, code in enumerate(aq.options_order)],
        "seconds_per_question": int(cfg["seconds_per_question"]),
        "deadline_at": aq.deadline_at.isoformat(),
        "server_now": now.isoformat(),
        "window_deadline_at": attempt.window_deadline_at.isoformat(),
        "allow_skip": bool(cfg.get("allow_skip", True)),
    }


def _finished_payload(s: Session, attempt: models.ExamAttempt) -> dict[str, Any]:
    r = s.get(models.AttemptResult, attempt.id)
    exam = s.get(models.Exam, attempt.exam_id)
    answered = s.scalar(
        select(func.count())
        .select_from(models.AttemptAnswer)
        .where(models.AttemptAnswer.attempt_id == attempt.id, models.AttemptAnswer.outcome.in_(["correct", "wrong"]))
    )
    body: dict[str, Any] = {
        "status": "finished",
        "folio": str(attempt.id)[:8].upper(),
        "exam": exam.name if exam else "",
        "full_name": attempt.full_name_entered,
        "finished_at": attempt.finished_at.isoformat() if attempt.finished_at else None,
        "total": int(attempt.config_snapshot["questions_per_attempt"]),
        "answered": answered,
        "omitted": (r.omitted if r else 0),
        "expired": (r.expired if r else 0),
        "reason": "window_expired" if attempt.status == "expired" else "completed",
    }
    if r and attempt.config_snapshot.get("show_grade_to_student"):
        body["grade"] = f"{float(r.grade):.2f}"
    return body


def current(token: str | None) -> dict[str, Any]:
    attempt_id, uni = _resolve(token)
    with db.tenant_session(uni) as s:
        return _advance(s, _locked_attempt(s, attempt_id))


def answer(token: str | None, ordinal: int, choice: int | None, idempotency_key: str) -> dict[str, Any]:
    if choice is not None and choice not in range(4):
        raise StudentError("Opción inválida.", 422)
    if not (8 <= len(idempotency_key) <= 64):
        raise StudentError("Solicitud inválida.", 422)
    attempt_id, uni = _resolve(token)
    with db.tenant_session(uni) as s:
        attempt = _locked_attempt(s, attempt_id)
        # Reintento de red: la misma clave ya se registró → devolver el estado actual sin duplicar.
        dup = s.scalar(
            select(models.AttemptAnswer.id).where(
                models.AttemptAnswer.attempt_id == attempt.id, models.AttemptAnswer.idempotency_key == idempotency_key
            )
        )
        if dup is not None:
            return _advance(s, attempt)
        finalize_if_expired(s, attempt)
        if attempt.status != "in_progress":
            return _finished_payload(s, attempt)
        if ordinal != attempt.current_ordinal:
            if ordinal < attempt.current_ordinal:
                return _advance(s, attempt)  # esa pregunta ya se cerró (expiró o se respondió)
            raise StudentError("Pregunta fuera de orden.", 409)
        aq = s.get(models.AttemptQuestion, (attempt.id, ordinal), with_for_update=True)
        assert aq is not None
        if aq.served_at is None:
            raise StudentError("Pregunta no servida.", 409)
        now = clock.now()
        if now > aq.deadline_at + _tolerance(attempt):
            _record(s, attempt, aq, outcome="expired", option_id=None, key=idempotency_key)
        elif choice is None:
            if not attempt.config_snapshot.get("allow_skip", True):
                raise StudentError("Este examen no permite omitir.", 422)
            _record(s, attempt, aq, outcome="omitted", option_id=None, key=idempotency_key)
        else:
            code = aq.options_order[choice]
            opt = s.scalar(
                select(models.QuestionOption).where(
                    models.QuestionOption.question_id == aq.question_id, models.QuestionOption.option_code == code
                )
            )
            assert opt is not None
            _record(
                s, attempt, aq, outcome="correct" if opt.is_correct else "wrong", option_id=opt.id, key=idempotency_key
            )
        return _advance(s, attempt)
