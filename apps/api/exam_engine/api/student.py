"""Endpoints del alumno. La sesión del intento viaja en cookie HttpOnly (nunca en localStorage)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ..config import get_settings
from ..services import attempts, clock
from .deps import client_ip, require_csrf

router = APIRouter(prefix="/student", tags=["alumno"], dependencies=[Depends(require_csrf)])
COOKIE = "mev_attempt"


class StartIn(BaseModel):
    access_code: str = Field(min_length=4, max_length=32)
    full_name: str = Field(min_length=1, max_length=200)
    matricula: str = Field(min_length=1, max_length=64)


class AnswerIn(BaseModel):
    ordinal: int = Field(ge=1, le=10_000)
    choice: int | None = Field(default=None, ge=0, le=3)
    idempotency_key: str = Field(min_length=8, max_length=64)


def _fail(exc: attempts.StudentError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=str(exc))


@router.post("/start")
def start(body: StartIn, request: Request, response: Response) -> dict[str, Any]:
    try:
        res = attempts.start(body.access_code, body.full_name, body.matricula, client_ip(request))
    except attempts.StudentError as exc:
        raise _fail(exc) from None
    max_age = int((res.window_deadline_at - clock.now() + timedelta(hours=2)).total_seconds())
    response.set_cookie(
        COOKIE,
        res.token,
        max_age=max(max_age, 60),
        httponly=True,
        secure=not get_settings().is_local,
        samesite="strict",
        path="/api/student",
    )
    return {"resumed": res.resumed}


@router.get("/current")
def current(request: Request) -> dict[str, Any]:
    try:
        return attempts.current(request.cookies.get(COOKIE))
    except attempts.StudentError as exc:
        raise _fail(exc) from None


@router.post("/answer")
def answer(body: AnswerIn, request: Request) -> dict[str, Any]:
    try:
        return attempts.answer(request.cookies.get(COOKIE), body.ordinal, body.choice, body.idempotency_key)
    except attempts.StudentError as exc:
        raise _fail(exc) from None
