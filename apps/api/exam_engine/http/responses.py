"""Respuestas HTTP JSON con cabeceras de seguridad uniformes."""

from __future__ import annotations

import json
from typing import Any

import azure.functions as func

SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


def json_response(body: Any, status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(body, ensure_ascii=False, default=str),
        status_code=status,
        mimetype="application/json",
        charset="utf-8",
        headers=SECURITY_HEADERS,
    )
