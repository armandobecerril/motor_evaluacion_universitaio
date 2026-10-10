"""Aplicación FastAPI (Azure App Service, Linux, Python 3.12).

Arranque en App Service:
    gunicorn -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:8000 exam_engine.main:app
"""

from __future__ import annotations

from fastapi import FastAPI, Request, Response

from .api import admin, health
from .config import get_settings

SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


def create_app() -> FastAPI:
    settings = get_settings()
    docs = settings.environment == "local"  # OpenAPI/Swagger solo en local
    app = FastAPI(
        title="Motor de Evaluación Universitario",
        version="0.2.0",
        docs_url="/api/docs" if docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs else None,
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        response: Response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        return response

    app.include_router(health.router, prefix="/api")
    app.include_router(admin.router, prefix="/api")
    return app


app = create_app()
