"""Endpoints del docente: revisión/aprobación de reactivos, exámenes y resultados."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import models
from ..services import exams as svc
from ..services.admin_auth import AdminPrincipal
from .deps import active_admin, admin_scope, load_course

router = APIRouter(prefix="/admin", tags=["docente-exámenes"])


def _err(exc: Exception) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


def _load_exam(s, p: AdminPrincipal, exam_id: uuid.UUID) -> models.Exam:  # type: ignore[no-untyped-def]
    exam = s.get(models.Exam, exam_id)
    if exam is None:
        raise HTTPException(status_code=404, detail="Examen no encontrado.")
    load_course(s, p, exam.course_id)  # verifica alcance del docente
    return exam


# ---------------------------------------------------------------- revisión ---


@router.get("/courses/{course_id}/questions")
def list_questions(
    course_id: uuid.UUID,
    module: int | None = None,
    status: str | None = Query(default=None, pattern="^(draft|reviewed|approved|retired)$"),
    q: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    p: AdminPrincipal = Depends(active_admin),
) -> dict[str, Any]:
    with admin_scope(p) as s:
        load_course(s, p, course_id)
        return svc.list_questions(s, course_id, module=module, status=status, q=q, page=page, size=size)


class StatusIn(BaseModel):
    action: str = Field(pattern="^(approve|retire)$")
    ids: list[uuid.UUID] | None = Field(default=None, max_length=1000)
    module: int | None = None
    all: bool = False


@router.post("/courses/{course_id}/questions/status")
def change_status(course_id: uuid.UUID, body: StatusIn, p: AdminPrincipal = Depends(active_admin)) -> dict[str, Any]:
    if not body.ids and not body.module and not body.all:
        raise HTTPException(status_code=422, detail="Indica ids, un módulo o 'all'.")
    with admin_scope(p) as s:
        course = load_course(s, p, course_id)
        n = svc.set_status(
            s,
            course,
            actor=p.username,
            reviewer_name=p.display_name,
            target_status="approved" if body.action == "approve" else "retired",
            ids=body.ids,
            module=body.module,
        )
    return {"updated": n}


# ------------------------------------------------------------------ exámenes ---


class ExamIn(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    code: str = Field(min_length=2, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    starts_at: datetime
    ends_at: datetime
    seconds_per_question: int | None = Field(default=None, ge=5, le=600)
    per_module_quota: int | None = Field(default=None, ge=1, le=500)
    max_variants_per_group: int | None = Field(default=None, ge=1, le=10)
    window_minutes: int | None = Field(default=None, ge=5, le=600)
    wrong_penalty: int | None = Field(default=None, ge=0, le=5)
    network_tolerance_ms: int | None = Field(default=None, ge=0, le=5000)
    show_grade_to_student: bool | None = None


class WindowIn(BaseModel):
    starts_at: datetime
    ends_at: datetime


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise HTTPException(status_code=422, detail="Las fechas deben incluir zona horaria.")
    return dt


@router.get("/courses/{course_id}/exams")
def list_exams(course_id: uuid.UUID, p: AdminPrincipal = Depends(active_admin)) -> list[dict[str, Any]]:
    from sqlalchemy import select

    with admin_scope(p) as s:
        load_course(s, p, course_id)
        exams = s.scalars(
            select(models.Exam).where(models.Exam.course_id == course_id).order_by(models.Exam.starts_at.desc())
        ).all()
        out = []
        for e in exams:
            d = svc.exam_dict(e)
            if e.status == "draft":
                d["readiness"] = svc.readiness(s, e)
            out.append(d)
        return out


@router.post("/courses/{course_id}/exams")
def create_exam(course_id: uuid.UUID, body: ExamIn, p: AdminPrincipal = Depends(active_admin)) -> dict[str, Any]:
    overrides = body.model_dump(exclude={"name", "code", "starts_at", "ends_at"})
    with admin_scope(p) as s:
        course = load_course(s, p, course_id)
        try:
            exam = svc.create_exam(
                s,
                course,
                actor=p.username,
                name=body.name,
                code=body.code,
                starts_at=_aware(body.starts_at),
                ends_at=_aware(body.ends_at),
                overrides=overrides,
            )
        except svc.ExamError as exc:
            raise _err(exc) from None
        d = svc.exam_dict(exam)
        d["readiness"] = svc.readiness(s, exam)
        return d


@router.post("/exams/{exam_id}/publish")
def publish(exam_id: uuid.UUID, p: AdminPrincipal = Depends(active_admin)) -> dict[str, Any]:
    with admin_scope(p) as s:
        exam = _load_exam(s, p, exam_id)
        try:
            code = svc.publish(s, exam, actor=p.username)
        except svc.ExamError as exc:
            raise _err(exc) from None
        return {**svc.exam_dict(exam), "access_code": code}


@router.post("/exams/{exam_id}/access-code")
def regenerate(exam_id: uuid.UUID, p: AdminPrincipal = Depends(active_admin)) -> dict[str, Any]:
    with admin_scope(p) as s:
        exam = _load_exam(s, p, exam_id)
        try:
            code = svc.regenerate_code(s, exam, actor=p.username)
        except svc.ExamError as exc:
            raise _err(exc) from None
        return {"access_code": code}


@router.post("/exams/{exam_id}/close")
def close(exam_id: uuid.UUID, p: AdminPrincipal = Depends(active_admin)) -> dict[str, Any]:
    with admin_scope(p) as s:
        exam = _load_exam(s, p, exam_id)
        try:
            svc.close(s, exam, actor=p.username)
        except svc.ExamError as exc:
            raise _err(exc) from None
        return svc.exam_dict(exam)


@router.post("/exams/{exam_id}/window")
def change_window(exam_id: uuid.UUID, body: WindowIn, p: AdminPrincipal = Depends(active_admin)) -> dict[str, Any]:
    with admin_scope(p) as s:
        exam = _load_exam(s, p, exam_id)
        try:
            svc.update_window(s, exam, actor=p.username, starts_at=_aware(body.starts_at), ends_at=_aware(body.ends_at))
        except svc.ExamError as exc:
            raise _err(exc) from None
        return svc.exam_dict(exam)


@router.get("/exams/{exam_id}/results")
def results(exam_id: uuid.UUID, p: AdminPrincipal = Depends(active_admin)) -> dict[str, Any]:
    with admin_scope(p) as s:
        exam = _load_exam(s, p, exam_id)
        rows = svc.results(s, exam)
        finished = [r for r in rows if r.grade is not None]
        avg = sum(float(r.grade) for r in finished) / len(finished) if finished else None
        return {
            "exam": svc.exam_dict(exam),
            "summary": {
                "attempts": len(rows),
                "in_progress": sum(1 for r in rows if r.status == "in_progress"),
                "finished": len(finished),
                "average": f"{avg:.2f}" if avg is not None else None,
            },
            "rows": [r.__dict__ for r in rows],
        }


@router.get("/exams/{exam_id}/results.csv")
def results_csv(exam_id: uuid.UUID, p: AdminPrincipal = Depends(active_admin)) -> Response:
    with admin_scope(p) as s:
        exam = _load_exam(s, p, exam_id)
        data = svc.results_csv(exam, svc.results(s, exam))
        name = f"resultados_{exam.code}.csv"
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
