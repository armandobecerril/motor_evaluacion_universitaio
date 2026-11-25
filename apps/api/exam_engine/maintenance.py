"""Mantenimiento del banco: retirar los reactivos de un banco ya expuesto (p. ej. una evaluación aplicada).

Retirar no afecta exámenes publicados: cada examen congela su conjunto de preguntas al publicarse
(exam_question) y los intentos se arman desde ese conjunto. Solo evita que los reactivos retirados
entren en exámenes que se creen y publiquen después.
"""

from __future__ import annotations

from collections import Counter

from sqlalchemy import select, update

from . import db, models
from .services.exams import audit


def retire_bank(university_code: str, course_code: str, bank_code: str, *, apply: bool) -> str:
    with db.tenant_session(None, platform_admin=True) as s:
        uni = s.scalar(select(models.University).where(models.University.code == university_code))
        if uni is None:
            raise SystemExit(f"No existe la universidad {university_code}.")
        course = s.scalar(
            select(models.Course).where(models.Course.university_id == uni.id, models.Course.code == course_code)
        )
        if course is None:
            raise SystemExit(f"No existe la materia {university_code}/{course_code}.")
        cond = (
            models.QuestionBank.course_id == course.id,
            models.QuestionBank.bank_code == bank_code,
            models.QuestionBank.is_current.is_(True),
            models.QuestionBank.status != "retired",
        )
        rows = s.execute(select(models.QuestionBank.module_number, models.QuestionBank.status).where(*cond)).all()
        if not rows:
            return (
                f"Nada que retirar: no hay reactivos vigentes del banco {bank_code} en {university_code}/{course_code}."
            )
        detail = " · ".join(f"M{m} {st}: {n}" for (m, st), n in sorted(Counter(rows).items()))
        if not apply:
            return f"[simulación] Se retirarían {len(rows)} reactivos del banco {bank_code} ({detail}). Usa --apply."
        n = s.execute(update(models.QuestionBank).where(*cond).values(status="retired")).rowcount or 0
        audit(s, uni.id, "cli", "questions.retired", count=n, bank_code=bank_code)
        return f"Retirados {n} reactivos del banco {bank_code} ({detail})."
