"""GET /api/health — estado del servicio sin secretos ni datos personales."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .. import db
from ..config import get_settings

router = APIRouter()
log = logging.getLogger(__name__)


@router.get("/health")
def health() -> JSONResponse:
    s = get_settings()
    payload: dict[str, object] = {
        "status": "ok",
        "environment": s.environment,
        "build": s.build_sha,
        "time_utc": datetime.now(UTC).isoformat(),
    }
    try:
        payload["database"] = "ok" if db.ping() else "error"
        payload["migration"] = db.current_migration()
    except Exception as exc:  # noqa: BLE001 — nunca exponer el detalle (puede incluir host/usuario)
        log.warning("health: base de datos no disponible (%s)", type(exc).__name__)
        payload["database"] = "unavailable"
        payload["migration"] = None
    status = 200 if payload["database"] == "ok" else 503
    if status != 200:
        payload["status"] = "degraded"
    return JSONResponse(payload, status_code=status)
