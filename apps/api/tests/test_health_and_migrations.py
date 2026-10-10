"""Health check y reversibilidad de migraciones."""

from __future__ import annotations

import json
import os

import azure.functions as func
from alembic import command
from sqlalchemy import create_engine, inspect

from exam_engine import db
from exam_engine.config import get_settings
from exam_engine.http.health import health


def _call_health() -> tuple[int, dict]:
    req = func.HttpRequest(method="GET", url="/api/health", body=b"")
    resp = health.build().get_user_function()(req)
    return resp.status_code, json.loads(resp.get_body())


def test_health_ok_reports_migration():
    status, body = _call_health()
    assert status == 200
    assert body["database"] == "ok"
    assert body["migration"] == "0001"


def test_health_degraded_does_not_leak_connection_details(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://usuario_secreto:clave_secreta@127.0.0.1:1/nodb")
    get_settings.cache_clear()
    db.reset_engine()
    try:
        status, body = _call_health()
        raw = json.dumps(body)
        assert status == 503
        assert body["database"] == "unavailable"
        for secret in ("usuario_secreto", "clave_secreta", "127.0.0.1"):
            assert secret not in raw
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        db.reset_engine()


def test_migrations_are_reversible(alembic_cfg):
    engine = create_engine(os.environ["TEST_MIGRATION_DATABASE_URL"])
    command.downgrade(alembic_cfg, "base")
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    command.upgrade(alembic_cfg, "head")
    assert "exam_sessions" in inspect(engine).get_table_names()
    engine.dispose()
    db.reset_engine()
