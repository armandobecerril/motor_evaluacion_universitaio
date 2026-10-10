"""Health check, cabeceras de seguridad y reversibilidad de migraciones."""

from __future__ import annotations

import json
import os

from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from exam_engine import db
from exam_engine.config import get_settings
from exam_engine.main import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_health_ok_reports_migration():
    r = _client().get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["database"] == "ok"
    assert body["migration"] == "0001"
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-content-type-options"] == "nosniff"


def test_health_degraded_does_not_leak_connection_details(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://usuario_secreto:clave_secreta@127.0.0.1:1/nodb")
    get_settings.cache_clear()
    db.reset_engine()
    try:
        r = _client().get("/api/health")
        raw = json.dumps(r.json())
        assert r.status_code == 503
        assert r.json()["database"] == "unavailable"
        for secret in ("usuario_secreto", "clave_secreta", "127.0.0.1"):
            assert secret not in raw
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        db.reset_engine()


def test_openapi_hidden_outside_local(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        c = _client()
        assert c.get("/api/docs").status_code == 404
        assert c.get("/api/openapi.json").status_code == 404
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_migrations_are_reversible(alembic_cfg):
    engine = create_engine(os.environ["TEST_MIGRATION_DATABASE_URL"])
    command.downgrade(alembic_cfg, "base")
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    command.upgrade(alembic_cfg, "head")
    assert "exam_attempts" in inspect(engine).get_table_names()
    engine.dispose()
    db.reset_engine()
