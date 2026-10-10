"""Flujo completo: aprobar → crear examen → publicar con código → alumno presenta → resultados."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from exam_engine import db, models
from exam_engine.main import create_app
from exam_engine.services import clock
from exam_engine.services.admin_auth import create_admin

from .conftest import make_bank

H = {"X-Requested-With": "mev"}
FORBIDDEN = ("correct", "rationale", "is_correct", "source_pdf", "conceptual_group", "external_id")


@pytest.fixture(autouse=True)
def real_clock():
    clock.set_now(None)
    yield
    clock.set_now(None)


@pytest.fixture()
def admin(course):
    username = f"doc{uuid.uuid4().hex[:6]}"
    create_admin(
        username=username,
        password="Clave-Segura-2026",
        display_name="Docente Prueba",
        role="platform_admin",
        university_code=None,
        temporary=False,
    )
    c = TestClient(create_app())
    assert (
        c.post("/api/admin/login", json={"username": username, "password": "Clave-Segura-2026"}, headers=H).status_code
        == 200
    )
    with db.tenant_session(None, platform_admin=True) as s:
        code = s.get(models.University, course.university_id).code
    files = {
        "file": (
            "banco.json",
            json.dumps(make_bank(code, groups_per_module=3, variants=4)).encode(),
            "application/json",
        )
    }
    assert c.post(f"/api/admin/courses/{course.id}/bank/import", files=files, headers=H).status_code == 200
    return c


def _create_exam(admin_client, course, **over):
    now = datetime.now(UTC)
    body = {
        "name": "Parcial 1",
        "code": f"P1-{uuid.uuid4().hex[:4]}",
        "starts_at": (now - timedelta(minutes=5)).isoformat(),
        "ends_at": (now + timedelta(hours=2)).isoformat(),
        "seconds_per_question": 20,
        "per_module_quota": 4,
        "max_variants_per_group": 2,
        "window_minutes": 60,
        **over,
    }
    r = admin_client.post(f"/api/admin/courses/{course.id}/exams", json=body, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def _approve_all(admin_client, course):
    r = admin_client.post(
        f"/api/admin/courses/{course.id}/questions/status", json={"action": "approve", "all": True}, headers=H
    )
    assert r.status_code == 200
    return r.json()["updated"]


def _published(admin_client, course, **over):
    _approve_all(admin_client, course)
    exam = _create_exam(admin_client, course, **over)
    r = admin_client.post(f"/api/admin/exams/{exam['id']}/publish", headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def _student(code, name="Ana María López", matricula="A00123"):
    c = TestClient(create_app())
    r = c.post("/api/student/start", json={"access_code": code, "full_name": name, "matricula": matricula}, headers=H)
    return c, r


def _no_keys(payload: dict) -> None:
    raw = json.dumps(payload)
    for k in FORBIDDEN:
        assert f'"{k}"' not in raw, f"fuga de '{k}' en respuesta de alumno"


# ------------------------------------------------------------------ docente ---


def test_publish_blocked_until_bank_is_approved(admin, course):
    exam = _create_exam(admin, course)
    assert exam["readiness"]["ready"] is False
    r = admin.post(f"/api/admin/exams/{exam['id']}/publish", headers=H)
    assert r.status_code == 422 and "insuficiente" in r.json()["detail"]


def test_review_list_shows_keys_only_to_teacher(admin, course):
    r = admin.get(f"/api/admin/courses/{course.id}/questions?module=1&size=5").json()
    assert r["total"] == 12 and len(r["items"]) == 5
    assert sum(o["correct"] for o in r["items"][0]["options"]) == 1


def test_approve_then_publish_freezes_pool_and_returns_code(admin, course):
    assert _approve_all(admin, course) == 48
    pub = _published(admin, course)
    assert pub["status"] == "published"
    assert len(pub["access_code"]) == 9 and pub["access_code"][4] == "-"
    with db.tenant_session(course.university_id) as s:
        n = s.scalar(
            select(func.count())
            .select_from(models.ExamQuestion)
            .where(models.ExamQuestion.exam_id == uuid.UUID(pub["id"]))
        )
        stored = s.get(models.Exam, uuid.UUID(pub["id"])).access_code_lookup
    assert n == 48
    assert pub["access_code"].replace("-", "") not in stored  # solo HMAC, nunca el código


def test_one_concept_per_attempt_blocks_publication(admin, course):
    _approve_all(admin, course)
    exam = _create_exam(admin, course, per_module_quota=4, max_variants_per_group=1)
    r = admin.post(f"/api/admin/exams/{exam['id']}/publish", headers=H)
    assert r.status_code == 422 and "M1: 3/4" in r.json()["detail"]


# ------------------------------------------------------------------- alumno ---


def test_student_flow_complete_and_results(admin, course):
    pub = _published(admin, course)
    c, r = _student(pub["access_code"].lower().replace("-", ""))  # tolera minúsculas y sin guion
    assert r.status_code == 200 and r.json()["resumed"] is False
    q = c.get("/api/student/current", headers=H).json()
    assert q["status"] == "in_progress" and q["ordinal"] == 1 and q["total"] == 16
    assert [o["label"] for o in q["options"]] == ["A", "B", "C", "D"]
    _no_keys(q)
    for i in range(16):
        body = {"ordinal": q["ordinal"], "choice": None if i % 4 == 3 else 0, "idempotency_key": uuid.uuid4().hex}
        q = c.post("/api/student/answer", json=body, headers=H).json()
        _no_keys(q)
    assert q["status"] == "finished" and q["total"] == 16 and q["omitted"] == 4
    assert "grade" not in q  # por defecto no se muestra la nota al alumno
    res = admin.get(f"/api/admin/exams/{pub['id']}/results").json()
    row = res["rows"][0]
    assert row["full_name"] == "Ana María López" and row["matricula"] == "A00123"
    assert row["correct"] + row["wrong"] + row["omitted"] + row["expired"] == 16
    expected = max(0, (row["correct"] - row["wrong"]) * 100 / 16)
    assert float(row["grade"]) == pytest.approx(expected, abs=0.005)
    assert res["summary"]["finished"] == 1


def test_selection_respects_quota_and_group_cap(admin, course):
    pub = _published(admin, course)
    _student(pub["access_code"])
    with db.tenant_session(course.university_id) as s:
        rows = s.execute(
            select(models.AttemptQuestion.module_number, models.QuestionBank.conceptual_group).join(
                models.QuestionBank, models.QuestionBank.id == models.AttemptQuestion.question_id
            )
        ).all()
    from collections import Counter

    assert Counter(m for m, _ in rows) == {1: 4, 2: 4, 3: 4, 4: 4}
    assert max(Counter(g for _, g in rows).values()) <= 2


def test_deadline_boundaries_server_time(admin, course):
    pub = _published(admin, course, seconds_per_question=20)
    c, _ = _student(pub["access_code"])
    t0 = datetime.now(UTC)
    clock.set_now(t0)
    q = c.get("/api/student/current", headers=H).json()
    clock.set_now(t0 + timedelta(seconds=19.999))
    q2 = c.post(
        "/api/student/answer", json={"ordinal": 1, "choice": 1, "idempotency_key": "k-0001-a"}, headers=H
    ).json()
    assert q2["ordinal"] == 2
    clock.set_now(t0 + timedelta(seconds=19.999 + 20.001))
    q3 = c.post(
        "/api/student/answer", json={"ordinal": 2, "choice": 1, "idempotency_key": "k-0002-a"}, headers=H
    ).json()
    assert q3["ordinal"] == 3
    with db.tenant_session(course.university_id) as s:
        outcomes = dict(s.execute(select(models.AttemptAnswer.ordinal, models.AttemptAnswer.outcome)).all())
    assert outcomes[1] in ("correct", "wrong") and outcomes[2] == "expired"
    assert q["seconds_per_question"] == 20


def test_reload_does_not_reset_deadline_and_expired_question_advances(admin, course):
    pub = _published(admin, course)
    c, _ = _student(pub["access_code"])
    t0 = datetime.now(UTC)
    clock.set_now(t0)
    a = c.get("/api/student/current", headers=H).json()
    clock.set_now(t0 + timedelta(seconds=10))
    b = c.get("/api/student/current", headers=H).json()
    assert a["deadline_at"] == b["deadline_at"] and b["ordinal"] == 1
    clock.set_now(t0 + timedelta(seconds=25))  # se venció sin responder → se omite y avanza
    d = c.get("/api/student/current", headers=H).json()
    assert d["ordinal"] == 2


def test_idempotent_retry_does_not_duplicate(admin, course):
    pub = _published(admin, course)
    c, _ = _student(pub["access_code"])
    c.get("/api/student/current", headers=H)
    body = {"ordinal": 1, "choice": 2, "idempotency_key": "retry-key-001"}
    r1 = c.post("/api/student/answer", json=body, headers=H).json()
    r2 = c.post("/api/student/answer", json=body, headers=H).json()
    assert r1["ordinal"] == r2["ordinal"] == 2
    with db.tenant_session(course.university_id) as s:
        assert s.scalar(select(func.count()).select_from(models.AttemptAnswer)) == 1


def test_single_attempt_and_resume_rules(admin, course):
    pub = _published(admin, course)
    c1, r1 = _student(pub["access_code"])
    first = c1.get("/api/student/current", headers=H).json()
    # Mismo nombre (sin acentos/mayúsculas) → reanuda el mismo intento; la sesión anterior queda inválida.
    c2, r2 = _student(pub["access_code"], name="ana maria lopez")
    assert r2.json()["resumed"] is True
    assert c2.get("/api/student/current", headers=H).json()["deadline_at"] == first["deadline_at"]
    assert c1.get("/api/student/current", headers=H).status_code == 401
    # Otro nombre con la misma matrícula → rechazado
    _, r3 = _student(pub["access_code"], name="Pedro Pérez Ruiz")
    assert r3.status_code == 409
    # Terminado → no puede volver a presentar
    clock.set_now(datetime.now(UTC) + timedelta(hours=3))
    c2.get("/api/student/current", headers=H)
    clock.set_now(None)
    _, r4 = _student(pub["access_code"])
    assert r4.status_code in (403, 409)


def test_window_expiry_closes_attempt_and_counts_unanswered(admin, course):
    pub = _published(admin, course, window_minutes=5)
    c, _ = _student(pub["access_code"])
    c.get("/api/student/current", headers=H)
    c.post("/api/student/answer", json={"ordinal": 1, "choice": 0, "idempotency_key": "w-key-0001"}, headers=H)
    clock.set_now(datetime.now(UTC) + timedelta(minutes=6))
    fin = c.get("/api/student/current", headers=H).json()
    assert fin["status"] == "finished" and fin["reason"] == "window_expired"
    row = admin.get(f"/api/admin/exams/{pub['id']}/results").json()["rows"][0]
    assert row["status"] == "expired" and row["expired"] == 15


def test_invalid_code_window_and_closed_exam(admin, course):
    _, r = _student("ZZZZ-ZZZZ")
    assert r.status_code == 404
    now = datetime.now(UTC)
    pub = _published(
        admin, course, starts_at=(now + timedelta(hours=1)).isoformat(), ends_at=(now + timedelta(hours=3)).isoformat()
    )
    _, r = _student(pub["access_code"])
    assert r.status_code == 403 and "abre el" in r.json()["detail"]
    admin.post(f"/api/admin/exams/{pub['id']}/close", headers=H)
    _, r = _student(pub["access_code"], matricula="B999")
    assert r.status_code == 403


def test_name_and_matricula_validation(admin, course):
    pub = _published(admin, course)
    _, r = _student(pub["access_code"], name="Ana")
    assert r.status_code == 422
    _, r = _student(pub["access_code"], matricula="A 1; DROP")
    assert r.status_code == 422


def test_csv_export_excel_friendly_and_safe(admin, course):
    pub = _published(admin, course)
    c, _ = _student(pub["access_code"], name="=HYPERLINK maliciosa", matricula="X001")
    r = admin.get(f"/api/admin/exams/{pub['id']}/results.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    text = r.content.decode("utf-8")
    assert text.startswith("﻿Folio,Nombre completo,Matrícula")
    assert "'=HYPERLINK maliciosa" in text


def test_student_cannot_use_admin_endpoints_and_csrf_required(admin, course):
    pub = _published(admin, course)
    c, _ = _student(pub["access_code"])
    assert c.get(f"/api/admin/exams/{pub['id']}/results").status_code == 401
    assert (
        c.post("/api/student/answer", json={"ordinal": 1, "choice": 0, "idempotency_key": "x" * 10}).status_code == 403
    )


def test_regenerated_code_invalidates_previous(admin, course):
    pub = _published(admin, course)
    new = admin.post(f"/api/admin/exams/{pub['id']}/access-code", headers=H).json()["access_code"]
    assert new != pub["access_code"]
    assert _student(pub["access_code"])[1].status_code == 404
    assert _student(new)[1].status_code == 200
