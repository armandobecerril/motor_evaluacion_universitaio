"""Aislamiento entre universidades mediante Row-Level Security (rol exam_app, no propietario)."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from exam_engine import db, models


def test_app_role_is_not_owner_nor_superuser():
    with db.tenant_session(None) as s:
        row = s.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")).one()
    assert row == (False, False), "las pruebas deben correr con un rol sin bypass de RLS"


def test_tenant_only_sees_its_own_rows(tenant_factory):
    a, b = tenant_factory(), tenant_factory()
    with db.tenant_session(a.id) as s:
        ids = set(s.scalars(select(models.Student.university_id)))
        subjects = set(s.scalars(select(models.Course.id)))
    assert ids == {a.id}
    assert b.course_id not in subjects


def test_without_tenant_context_nothing_is_visible(tenant_factory):
    tenant_factory()
    with db.tenant_session(None) as s:
        assert s.scalar(select(func.count()).select_from(models.Student)) == 0
        assert s.scalar(select(func.count()).select_from(models.Exam)) == 0


def test_cannot_write_into_another_tenant(tenant_factory):
    a, b = tenant_factory(), tenant_factory()
    with pytest.raises(DBAPIError, match="row-level security"):
        with db.tenant_session(a.id) as s:
            s.add(models.Student(university_id=b.id, matricula="X999", full_name="Intruso"))
            s.flush()


def test_cannot_update_other_tenant_rows(tenant_factory):
    a, b = tenant_factory(), tenant_factory()
    with db.tenant_session(a.id) as s:
        result = s.execute(text("UPDATE students SET full_name = 'hack' WHERE university_id = :b"), {"b": str(b.id)})
        assert result.rowcount == 0


def test_tenant_context_does_not_leak_between_transactions(tenant_factory):
    a = tenant_factory()
    with db.tenant_session(a.id) as s:
        assert s.scalar(select(func.count()).select_from(models.Student)) >= 1
    # Nueva transacción (probablemente la misma conexión del pool) sin contexto: no ve nada.
    with db.tenant_session(None) as s:
        assert s.scalar(text("SELECT current_setting('app.university_id', true)")) in (None, "")
        assert s.scalar(select(func.count()).select_from(models.Student)) == 0


def test_platform_admin_sees_all(tenant_factory):
    a, b = tenant_factory(), tenant_factory()
    with db.tenant_session(None, platform_admin=True) as s:
        ids = set(s.scalars(select(models.Student.university_id)))
    assert {a.id, b.id} <= ids
