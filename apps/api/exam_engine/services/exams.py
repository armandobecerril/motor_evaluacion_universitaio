"""Operaciones del docente: aprobación de reactivos, exámenes (crear/publicar/cerrar) y resultados."""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models
from ..config import get_settings
from ..security import access_code_lookup, new_access_code
from . import clock
from .selection import PoolItem, feasibility

DEFAULT_CONFIG: dict[str, Any] = {
    "per_module_quota": 50,
    "max_variants_per_group": 2,
    "selection": "balanced_by_group",
    "seconds_per_question": 30,
    "network_tolerance_ms": 0,
    "window_minutes": 120,
    "scoring": {"correct": 1, "wrong": -1, "omitted": 0, "expired": 0},
    "allow_skip": True,
    "attempts_per_student": 1,
    "show_grade_to_student": False,
    "timezone": "America/Mexico_City",
}
EDITABLE_KEYS = {
    "per_module_quota",
    "max_variants_per_group",
    "seconds_per_question",
    "network_tolerance_ms",
    "window_minutes",
    "show_grade_to_student",
    "wrong_penalty",
}


class ExamError(ValueError):
    pass


def audit(s: Session, university_id, actor: str, event: str, attempt_id=None, **meta: Any) -> None:  # type: ignore[no-untyped-def]
    s.add(
        models.AuditEvent(
            university_id=university_id,
            actor_type="admin" if actor not in ("system", "student") else actor,
            actor_id=actor,
            attempt_id=attempt_id,
            event_type=event,
            event_metadata=meta,
        )
    )


def module_numbers(s: Session, course_id: uuid.UUID) -> list[int]:
    return sorted(
        s.scalars(select(models.CourseModule.module_number).where(models.CourseModule.course_id == course_id))
    )


# ------------------------------------------------------------------ revisión ---


def list_questions(
    s: Session, course_id: uuid.UUID, *, module: int | None, status: str | None, q: str | None, page: int, size: int
) -> dict[str, Any]:
    base = select(models.QuestionBank).where(
        models.QuestionBank.course_id == course_id, models.QuestionBank.is_current.is_(True)
    )
    if module:
        base = base.where(models.QuestionBank.module_number == module)
    if status:
        base = base.where(models.QuestionBank.status == status)
    if q:
        like = f"%{q.strip()}%"
        base = base.where(
            models.QuestionBank.stem.ilike(like)
            | models.QuestionBank.topic.ilike(like)
            | models.QuestionBank.external_id.ilike(like)
        )
    total = s.scalar(select(func.count()).select_from(base.subquery()))
    rows = s.scalars(base.order_by(models.QuestionBank.external_id).offset((page - 1) * size).limit(size)).all()
    ids = [r.id for r in rows]
    opts: dict[uuid.UUID, list[models.QuestionOption]] = {}
    for o in s.scalars(
        select(models.QuestionOption)
        .where(models.QuestionOption.question_id.in_(ids))
        .order_by(models.QuestionOption.option_code)
    ):
        opts.setdefault(o.question_id, []).append(o)
    return {
        "total": total,
        "page": page,
        "items": [
            {
                "id": str(r.id),
                "external_id": r.external_id,
                "version": r.version,
                "module": r.module_number,
                "topic": r.topic,
                "conceptual_group": r.conceptual_group,
                "case_type": r.case_type,
                "bloom": r.bloom,
                "difficulty": r.difficulty,
                "stem": r.stem,
                "options": [
                    {"code": o.option_code, "text": o.text, "correct": o.is_correct} for o in opts.get(r.id, [])
                ],
                "rationale": r.rationale,
                "status": r.status,
                "reviewer": r.reviewer,
                "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
            }
            for r in rows
        ],
    }


def set_status(
    s: Session,
    course: models.Course,
    *,
    actor: str,
    reviewer_name: str,
    target_status: str,
    ids: list[uuid.UUID] | None,
    module: int | None,
) -> int:
    """Aprueba (o retira) reactivos vigentes. El trigger de la BD exige 4 opciones/1 correcta."""
    if target_status not in ("approved", "retired"):
        raise ExamError("Estado no permitido.")
    cond = [models.QuestionBank.course_id == course.id, models.QuestionBank.is_current.is_(True)]
    if target_status == "approved":
        cond.append(models.QuestionBank.status.in_(["draft", "reviewed"]))
    else:
        cond.append(models.QuestionBank.status != "retired")
    if ids:
        cond.append(models.QuestionBank.id.in_(ids))
    elif module:
        cond.append(models.QuestionBank.module_number == module)
    values: dict[str, Any] = {"status": target_status}
    if target_status == "approved":
        values.update(reviewer=reviewer_name, reviewed_at=clock.now())
    res = s.execute(update(models.QuestionBank).where(*cond).values(**values))
    n = res.rowcount or 0
    audit(
        s,
        course.university_id,
        actor,
        f"questions.{target_status}",
        count=n,
        module=module,
        ids=[str(i) for i in ids][:500] if ids else None,
    )
    return n


# ------------------------------------------------------------------- exámenes ---


def build_config(course: models.Course, modules: list[int], overrides: dict[str, Any]) -> dict[str, Any]:
    cfg = {**DEFAULT_CONFIG, **{k: v for k, v in (course.config or {}).items() if k in DEFAULT_CONFIG}}
    cfg["scoring"] = dict(cfg["scoring"])
    for k, v in overrides.items():
        if k not in EDITABLE_KEYS or v is None:
            continue
        if k == "wrong_penalty":
            cfg["scoring"]["wrong"] = -abs(int(v))
        else:
            cfg[k] = v
    if not (5 <= int(cfg["seconds_per_question"]) <= 600):
        raise ExamError("Segundos por pregunta fuera de rango (5–600).")
    if int(cfg["per_module_quota"]) < 1 or int(cfg["max_variants_per_group"]) < 1:
        raise ExamError("Cuota por módulo y variantes por concepto deben ser ≥ 1.")
    cfg["modules"] = modules
    cfg["questions_per_attempt"] = int(cfg["per_module_quota"]) * len(modules)
    return cfg


def exam_dict(e: models.Exam) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "code": e.code,
        "name": e.name,
        "status": e.status,
        "starts_at": e.starts_at.isoformat(),
        "ends_at": e.ends_at.isoformat(),
        "config": e.config,
        "published_at": e.published_at.isoformat() if e.published_at else None,
        "has_access_code": e.access_code_lookup is not None,
    }


def create_exam(
    s: Session,
    course: models.Course,
    *,
    actor: str,
    name: str,
    code: str,
    starts_at: datetime,
    ends_at: datetime,
    overrides: dict[str, Any],
) -> models.Exam:
    if ends_at <= starts_at:
        raise ExamError("La fecha de cierre debe ser posterior a la de apertura.")
    cfg = build_config(course, module_numbers(s, course.id), overrides)
    exam = models.Exam(
        university_id=course.university_id,
        course_id=course.id,
        code=code.strip().upper()[:32],
        name=name.strip()[:200],
        starts_at=starts_at,
        ends_at=ends_at,
        status="draft",
        config=cfg,
    )
    s.add(exam)
    try:
        s.flush()
    except IntegrityError as exc:
        raise ExamError("Ya existe un examen con ese identificador en la materia.") from exc
    audit(s, course.university_id, actor, "exam.created", exam_id=str(exam.id), config=cfg)
    return exam


def _approved_pool(s: Session, course_id: uuid.UUID) -> list[tuple[uuid.UUID, int, str]]:
    return s.execute(
        select(models.QuestionBank.id, models.QuestionBank.module_number, models.QuestionBank.conceptual_group).where(
            models.QuestionBank.course_id == course_id,
            models.QuestionBank.is_current.is_(True),
            models.QuestionBank.status == "approved",
        )
    ).all()


def readiness(s: Session, exam: models.Exam) -> dict[str, Any]:
    cfg = exam.config
    pool = [PoolItem(qid, m, g) for qid, m, g in _approved_pool(s, exam.course_id)]
    feas = feasibility(pool, cfg["modules"], cfg["per_module_quota"], cfg["max_variants_per_group"])
    approved = {m: sum(1 for p in pool if p.module_number == m) for m in cfg["modules"]}
    modules = [
        {"module": m, "approved": approved[m], "selectable": feas[m], "required": cfg["per_module_quota"]}
        for m in cfg["modules"]
    ]
    return {"ready": all(x["selectable"] >= x["required"] for x in modules), "modules": modules}


def _format_code(code: str) -> str:
    return f"{code[:4]}-{code[4:]}"


def _assign_code(s: Session, exam: models.Exam) -> str:
    pepper = get_settings().access_code_pepper.get_secret_value()
    for _ in range(5):
        code = new_access_code(8)
        lookup = access_code_lookup(code, pepper)
        if s.scalar(select(models.Exam.id).where(models.Exam.access_code_lookup == lookup)) is None:
            exam.access_code_lookup = lookup
            return _format_code(code)
    raise ExamError("No se pudo generar un código único; reintenta.")  # pragma: no cover


def publish(s: Session, exam: models.Exam, *, actor: str) -> str:
    """Congela el pool aprobado, genera el código de acceso y publica. Devuelve el código (se muestra 1 vez)."""
    if exam.status != "draft":
        raise ExamError("Solo se puede publicar un examen en borrador.")
    r = readiness(s, exam)
    if not r["ready"]:
        detail = "; ".join(
            f"M{x['module']}: {x['selectable']}/{x['required']} seleccionables ({x['approved']} aprobados)"
            for x in r["modules"]
            if x["selectable"] < x["required"]
        )
        raise ExamError(f"Banco aprobado insuficiente para la configuración: {detail}.")
    pool = _approved_pool(s, exam.course_id)
    s.add_all(
        models.ExamQuestion(exam_id=exam.id, question_id=qid, university_id=exam.university_id) for qid, _, _ in pool
    )
    code = _assign_code(s, exam)
    exam.status = "published"
    exam.published_at = clock.now()
    exam.published_by = actor
    s.flush()
    audit(s, exam.university_id, actor, "exam.published", exam_id=str(exam.id), pool_size=len(pool))
    return code


def regenerate_code(s: Session, exam: models.Exam, *, actor: str) -> str:
    if exam.status != "published":
        raise ExamError("Solo un examen publicado tiene código de acceso.")
    code = _assign_code(s, exam)
    s.flush()
    audit(s, exam.university_id, actor, "exam.code_regenerated", exam_id=str(exam.id))
    return code


def close(s: Session, exam: models.Exam, *, actor: str) -> None:
    if exam.status != "published":
        raise ExamError("Solo se puede cerrar un examen publicado.")
    exam.status = "closed"
    audit(s, exam.university_id, actor, "exam.closed", exam_id=str(exam.id))


def update_window(s: Session, exam: models.Exam, *, actor: str, starts_at: datetime, ends_at: datetime) -> None:
    if ends_at <= starts_at:
        raise ExamError("La fecha de cierre debe ser posterior a la de apertura.")
    if exam.status not in ("draft", "published"):
        raise ExamError("El examen ya está cerrado.")
    exam.starts_at, exam.ends_at = starts_at, ends_at
    audit(
        s,
        exam.university_id,
        actor,
        "exam.window_changed",
        exam_id=str(exam.id),
        starts_at=starts_at.isoformat(),
        ends_at=ends_at.isoformat(),
    )


# ------------------------------------------------------------------ resultados ---


@dataclass
class ResultRow:
    attempt_id: str
    folio: str
    full_name: str
    matricula: str
    status: str
    started_at: str
    finished_at: str | None
    answered: int
    total: int
    correct: int | None
    wrong: int | None
    omitted: int | None
    expired: int | None
    grade: str | None


def results(s: Session, exam: models.Exam) -> list[ResultRow]:
    from .attempts import finalize_if_expired  # evitar import circular

    attempts = s.scalars(
        select(models.ExamAttempt).where(models.ExamAttempt.exam_id == exam.id).order_by(models.ExamAttempt.started_at)
    ).all()
    for a in attempts:  # cierra automáticamente intentos cuya ventana ya venció
        finalize_if_expired(s, a)
    s.flush()
    students = {
        st.id: st
        for st in s.scalars(select(models.Student).where(models.Student.id.in_([a.student_id for a in attempts])))
    }
    res = {
        r.attempt_id: r
        for r in s.scalars(
            select(models.AttemptResult).where(models.AttemptResult.attempt_id.in_([a.id for a in attempts]))
        )
    }
    answered = dict(
        s.execute(
            select(models.AttemptAnswer.attempt_id, func.count())
            .where(models.AttemptAnswer.attempt_id.in_([a.id for a in attempts]))
            .group_by(models.AttemptAnswer.attempt_id)
        ).all()
    )
    out = []
    for a in attempts:
        r = res.get(a.id)
        st = students[a.student_id]
        out.append(
            ResultRow(
                attempt_id=str(a.id),
                folio=str(a.id)[:8].upper(),
                full_name=a.full_name_entered,
                matricula=st.matricula,
                status=a.status,
                started_at=a.started_at.isoformat(),
                finished_at=a.finished_at.isoformat() if a.finished_at else None,
                answered=answered.get(a.id, 0),
                total=a.config_snapshot["questions_per_attempt"],
                correct=r.correct if r else None,
                wrong=r.wrong if r else None,
                omitted=r.omitted if r else None,
                expired=r.expired if r else None,
                grade=f"{float(r.grade):.2f}" if r else None,
            )
        )
    return out


STATUS_ES = {"in_progress": "En curso", "finished": "Terminado", "expired": "Tiempo agotado", "voided": "Anulado"}


def results_csv(exam: models.Exam, rows: list[ResultRow], tz_offset_minutes: int = -360) -> bytes:
    """CSV para Excel: UTF-8 con BOM, separador coma, decimales con punto (configuración regional de México)."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(
        [
            "Folio",
            "Nombre completo",
            "Matrícula",
            "Estado",
            "Inicio",
            "Fin",
            "Avance",
            "Total",
            "Correctas",
            "Incorrectas",
            "Omitidas",
            "Expiradas",
            "Calificación",
        ]
    )
    tz = timedelta(minutes=tz_offset_minutes)

    def local(iso: str | None) -> str:
        if not iso:
            return ""
        return (datetime.fromisoformat(iso) + tz).strftime("%Y-%m-%d %H:%M:%S")

    for r in rows:
        w.writerow(
            [
                r.folio,
                _safe(r.full_name),
                _safe(r.matricula),
                STATUS_ES.get(r.status, r.status),
                local(r.started_at),
                local(r.finished_at),
                r.answered,
                r.total,
                _n(r.correct),
                _n(r.wrong),
                _n(r.omitted),
                _n(r.expired),
                r.grade or "",
            ]
        )
    return ("﻿" + buf.getvalue()).encode("utf-8")


def _n(v: int | None) -> str:
    return "" if v is None else str(v)


def _safe(text: str) -> str:
    """Evita inyección de fórmulas en Excel (=, +, -, @ al inicio)."""
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text
