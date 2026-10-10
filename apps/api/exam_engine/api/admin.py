"""Endpoints del docente: sesión, catálogo y banco de preguntas."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from .. import models
from ..config import get_settings
from ..services import admin_auth
from ..services.admin_auth import AdminPrincipal, LoginError
from ..services.bank_import import import_bank, parse_and_validate
from ..services.quality import build_report, render_markdown
from .deps import ADMIN_COOKIE, active_admin, admin_scope, client_ip, current_admin, load_course, require_csrf

router = APIRouter(prefix="/admin", tags=["docente"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class PasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


def _me(p: AdminPrincipal) -> dict[str, Any]:
    return {
        "username": p.username,
        "display_name": p.display_name,
        "role": p.role,
        "must_change_password": p.must_change_password,
    }


@router.post("/login", dependencies=[Depends(require_csrf)])
def login(body: LoginIn, request: Request, response: Response) -> dict[str, Any]:
    try:
        principal, token = admin_auth.login(body.username, body.password, client_ip(request))
    except LoginError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from None
    s = get_settings()
    response.set_cookie(
        ADMIN_COOKIE,
        token,
        max_age=s.admin_session_hours * 3600,
        httponly=True,
        secure=not s.is_local,
        samesite="strict",
        path="/api",
    )
    return _me(principal)


@router.post("/logout", dependencies=[Depends(require_csrf)])
def logout(request: Request, response: Response) -> dict[str, str]:
    admin_auth.logout(request.cookies.get(ADMIN_COOKIE))
    response.delete_cookie(ADMIN_COOKIE, path="/api")
    return {"status": "ok"}


@router.get("/me")
def me(p: AdminPrincipal = Depends(current_admin)) -> dict[str, Any]:
    return _me(p)


@router.post("/password")
def change_password(body: PasswordIn, p: AdminPrincipal = Depends(current_admin)) -> dict[str, Any]:
    problems = admin_auth.change_password(p, body.current_password, body.new_password)
    if problems:
        raise HTTPException(status_code=422, detail=problems)
    return {"status": "ok", "message": "Contraseña actualizada. Vuelve a iniciar sesión."}


@router.get("/catalog")
def catalog(p: AdminPrincipal = Depends(active_admin)) -> list[dict[str, Any]]:
    with admin_scope(p) as s:
        rows = s.execute(
            select(models.University, models.Course)
            .join(models.Course, models.Course.university_id == models.University.id)
            .order_by(models.University.code, models.Course.name)
        ).all()
        out: list[dict[str, Any]] = []
        for uni, course in rows:
            if p.role == "teacher":
                try:
                    load_course(s, p, course.id)
                except HTTPException:
                    continue
            out.append(
                {
                    "university": {"id": str(uni.id), "code": uni.code, "name": uni.name},
                    "course": {"id": str(course.id), "code": course.code, "name": course.name},
                }
            )
        return out


async def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    limit = get_settings().max_bank_upload_bytes
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status_code=413, detail=f"El archivo supera {limit // 1_000_000} MB.")
    name = (file.filename or "banco.json").rsplit("/", 1)[-1]
    if not name.lower().endswith((".json", ".csv")):
        raise HTTPException(status_code=415, detail="Sube un archivo .json o .csv.")
    return data, name


def _report(s, course: models.Course, items, quota: int, max_variants: int, seconds: int):  # type: ignore[no-untyped-def]
    pages = {
        src.file_name: src.page_count
        for src in s.scalars(select(models.CourseSource).where(models.CourseSource.course_id == course.id))
    }
    rep = build_report(
        items,
        per_module_quota=quota,
        max_variants_per_group=max_variants,
        seconds_per_question=seconds,
        source_pages=pages,
    )
    note = (
        f"Configuración evaluada: {quota} por módulo, máx. {max_variants} variante(s) por grupo conceptual, "
        f"{seconds} s por pregunta."
    )
    return rep, render_markdown(rep, course.name, note)


@router.post("/courses/{course_id}/bank/validate")
async def validate_bank(
    course_id: uuid.UUID,
    file: UploadFile = File(...),
    per_module_quota: int = 50,
    max_variants_per_group: int = 2,
    seconds_per_question: int = 20,
    p: AdminPrincipal = Depends(active_admin),
) -> dict[str, Any]:
    """Validación en seco: no escribe nada. Devuelve errores, advertencias y reporte de calidad (sin claves)."""
    data, name = await _read_upload(file)
    with admin_scope(p) as s:
        course = load_course(s, p, course_id)
        try:
            bank = parse_and_validate(s, course, data, name)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        rep, md = _report(s, course, bank.items, per_module_quota, max_variants_per_group, seconds_per_question)
        return {
            "valid": not bank.errors,
            "bank_code": bank.bank_code,
            "items": len(bank.items),
            "errors": bank.errors[:200],
            "error_count": len(bank.errors),
            "warnings": bank.warnings,
            "blocking": rep.blocking,
            "findings": [{"level": lvl, "text": txt} for lvl, txt in rep.findings],
            "totals": rep.totals,
            "report_markdown": md,
        }


@router.post("/courses/{course_id}/bank/import")
async def import_bank_endpoint(
    course_id: uuid.UUID, file: UploadFile = File(...), p: AdminPrincipal = Depends(active_admin)
) -> dict[str, Any]:
    data, name = await _read_upload(file)
    with admin_scope(p) as s:
        course = load_course(s, p, course_id)
        try:
            res = import_bank(s, course, data, name, actor=p.username)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
    if not res.ok:
        raise HTTPException(status_code=422, detail={"errors": res.errors, "warnings": res.warnings})
    return {
        "import_id": str(res.import_id),
        "bank_code": res.bank_code,
        "total": res.total,
        "created": res.created,
        "new_versions": res.new_versions,
        "unchanged": res.unchanged,
        "warnings": res.warnings,
        "conceptual_group_changes": res.group_changes[:100],
    }


@router.get("/courses/{course_id}/bank/summary")
def bank_summary(course_id: uuid.UUID, p: AdminPrincipal = Depends(active_admin)) -> dict[str, Any]:
    with admin_scope(p) as s:
        course = load_course(s, p, course_id)
        rows = s.execute(
            select(models.QuestionBank.module_number, models.QuestionBank.status, func.count())
            .where(models.QuestionBank.course_id == course.id, models.QuestionBank.is_current.is_(True))
            .group_by(models.QuestionBank.module_number, models.QuestionBank.status)
        ).all()
        by_module: dict[int, dict[str, int]] = {}
        for module, status, count in rows:
            by_module.setdefault(module, {})[status] = count
        return {"course": course.name, "modules": by_module, "total": sum(c for *_, c in rows)}
