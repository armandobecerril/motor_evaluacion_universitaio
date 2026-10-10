"""API del docente: login, bloqueo, CSRF, contraseña temporal, validación e importación por HTTP."""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from exam_engine import db, models
from exam_engine.main import create_app
from exam_engine.services.admin_auth import create_admin

from .conftest import make_bank

H = {"X-Requested-With": "mev"}


@pytest.fixture()
def admin_user():
    username = f"adm{uuid.uuid4().hex[:6]}"
    create_admin(
        username=username,
        password="Clave-Segura-2026",
        display_name="Docente",
        role="platform_admin",
        university_code=None,
        temporary=False,
    )
    return username


def _login(c: TestClient, username: str, password: str = "Clave-Segura-2026"):
    return c.post("/api/admin/login", json={"username": username, "password": password}, headers=H)


def test_login_sets_httponly_cookie_and_me_works(admin_user):
    c = TestClient(create_app())
    r = _login(c, admin_user)
    assert r.status_code == 200 and r.json()["role"] == "platform_admin"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/api" in cookie
    assert c.get("/api/admin/me").json()["username"] == admin_user


def test_wrong_password_and_unknown_user_same_message(admin_user):
    c = TestClient(create_app())
    a = _login(c, admin_user, "mala")
    b = _login(c, "no-existe", "mala")
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_lockout_after_failed_attempts(admin_user):
    c = TestClient(create_app())
    for _ in range(5):
        assert _login(c, admin_user, "mala").status_code == 401
    assert _login(c, admin_user).status_code == 423  # aun con la contraseña correcta


def test_csrf_header_required_for_mutations(admin_user):
    c = TestClient(create_app())
    r = c.post("/api/admin/login", json={"username": admin_user, "password": "Clave-Segura-2026"})
    assert r.status_code == 403


def test_endpoints_require_session():
    c = TestClient(create_app())
    assert c.get("/api/admin/me").status_code == 401
    assert c.get("/api/admin/catalog").status_code == 401


def test_temporary_password_must_be_changed():
    username = f"tmp{uuid.uuid4().hex[:6]}"
    create_admin(
        username=username,
        password="Password123$",
        display_name="Admin",
        role="platform_admin",
        university_code=None,
        temporary=True,
    )
    c = TestClient(create_app())
    r = _login(c, username, "Password123$")
    assert r.status_code == 200 and r.json()["must_change_password"] is True
    assert c.get("/api/admin/catalog").status_code == 403
    weak = c.post(
        "/api/admin/password", json={"current_password": "Password123$", "new_password": "Password123$"}, headers=H
    )
    assert weak.status_code == 422
    ok = c.post(
        "/api/admin/password", json={"current_password": "Password123$", "new_password": "Finanzas-UDL-2026"}, headers=H
    )
    assert ok.status_code == 200
    assert c.get("/api/admin/me").status_code == 401  # sesiones revocadas tras el cambio
    assert _login(c, username, "Finanzas-UDL-2026").json()["must_change_password"] is False


def test_validate_then_import_via_http(admin_user, course):
    with db.tenant_session(None, platform_admin=True) as s:
        code = s.get(models.University, course.university_id).code
    c = TestClient(create_app())
    _login(c, admin_user)
    data = json.dumps(make_bank(code, groups_per_module=3, variants=4)).encode()
    files = {"file": ("banco.json", data, "application/json")}
    v = c.post(
        f"/api/admin/courses/{course.id}/bank/validate?per_module_quota=5&max_variants_per_group=2",
        files=files,
        headers=H,
    )
    assert v.status_code == 200
    body = v.json()
    assert body["valid"] and body["items"] == 48 and body["blocking"] is False
    assert "Opción A del caso" not in json.dumps(body)  # el reporte no expone opciones ni claves
    i = c.post(f"/api/admin/courses/{course.id}/bank/import", files=files, headers=H)
    assert i.status_code == 200 and i.json()["created"] == 48
    again = c.post(f"/api/admin/courses/{course.id}/bank/import", files=files, headers=H)
    assert again.json()["unchanged"] == 48
    summary = c.get(f"/api/admin/courses/{course.id}/bank/summary").json()
    assert summary["total"] == 48 and summary["modules"]["1"]["draft"] == 12


def test_upload_type_and_size_limits(admin_user, course):
    c = TestClient(create_app())
    _login(c, admin_user)
    r = c.post(
        f"/api/admin/courses/{course.id}/bank/validate",
        files={"file": ("x.exe", b"MZ", "application/octet-stream")},
        headers=H,
    )
    assert r.status_code == 415
