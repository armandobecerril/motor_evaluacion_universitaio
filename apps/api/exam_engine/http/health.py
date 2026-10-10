"""GET /api/health — estado del servicio sin secretos ni datos personales."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import azure.functions as func

from .. import db
from ..config import get_settings
from .responses import json_response

bp = func.Blueprint()
log = logging.getLogger(__name__)


def health_payload() -> tuple[dict[str, object], int]:
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
    return payload, status


@bp.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health(req: func.HttpRequest) -> func.HttpResponse:
    body, status = health_payload()
    return json_response(body, status)
