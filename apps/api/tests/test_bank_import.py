"""Importador del banco: validación todo-o-nada, idempotencia, versionado y aislamiento."""

from __future__ import annotations

import copy
import json

from sqlalchemy import func, select

from exam_engine import db, models
from exam_engine.services.bank_import import import_bank

from .conftest import make_bank


def _uni_code(course) -> str:
    with db.tenant_session(None, platform_admin=True) as s:
        return s.get(models.University, course.university_id).code


def _import(course, bank: dict, dry_run: bool = False):
    with db.tenant_session(course.university_id) as s:
        c = s.get(models.Course, course.id)
        return import_bank(s, c, json.dumps(bank).encode(), "banco.json", actor="pytest", dry_run=dry_run)


def _count(course, **filters) -> int:
    with db.tenant_session(course.university_id) as s:
        q = select(func.count()).select_from(models.QuestionBank).where(models.QuestionBank.course_id == course.id)
        for k, v in filters.items():
            q = q.where(getattr(models.QuestionBank, k) == v)
        return s.scalar(q)


def test_import_creates_all_as_draft_with_options(course):
    bank = make_bank(_uni_code(course))
    res = _import(course, bank)
    assert res.ok and res.created == 24 and res.unchanged == 0
    assert _count(course) == 24
    assert _count(course, status="draft") == 24
    with db.tenant_session(course.university_id) as s:
        n_opts = s.scalar(select(func.count()).select_from(models.QuestionOption))
        n_ok = s.scalar(select(func.count()).select_from(models.QuestionOption).where(models.QuestionOption.is_correct))
        q = s.scalar(select(models.QuestionBank).where(models.QuestionBank.external_id == "T-0001"))
    assert (n_opts, n_ok) == (96, 24)
    assert q.conceptual_group == "M01-C01" and q.source_page is None and q.case_type == "diagnóstico"
    assert any("ready_for_professor_review" in w for w in res.warnings)


def test_reimport_same_file_is_idempotent(course):
    bank = make_bank(_uni_code(course))
    _import(course, bank)
    res = _import(course, bank)
    assert (res.created, res.new_versions, res.unchanged) == (0, 0, 24)
    assert _count(course) == 24


def test_changed_question_creates_new_version_and_keeps_history(course):
    bank = make_bank(_uni_code(course))
    _import(course, bank)
    changed = copy.deepcopy(bank)
    changed["questions"][0]["stem"] = "Enunciado corregido por el docente. ¿Qué conviene?"
    changed["questions"][1]["concept_id"] = "M01-C99"
    res = _import(course, changed)
    assert (res.created, res.new_versions, res.unchanged) == (0, 2, 22)
    assert res.group_changes == ["T-0002: M01-C01 → M01-C99"]
    assert _count(course) == 26 and _count(course, is_current=True) == 24
    with db.tenant_session(course.university_id) as s:
        versions = s.scalars(
            select(models.QuestionBank.version)
            .where(models.QuestionBank.external_id == "T-0001")
            .order_by(models.QuestionBank.version)
        ).all()
        audits = s.scalar(
            select(func.count())
            .select_from(models.AuditEvent)
            .where(models.AuditEvent.event_type == "question.new_version")
        )
    assert versions == [1, 2] and audits == 2


def test_any_error_rejects_whole_file(course):
    bank = make_bank(_uni_code(course))
    bank["questions"][5]["options"] = bank["questions"][5]["options"][:3]
    bank["questions"][6]["source_pdf"] = "01_Knight Capital(1).pdf"
    bank["questions"][7]["module"] = 9
    res = _import(course, bank)
    assert not res.ok
    text = " ".join(res.errors)
    assert "4 opciones" in text and "solo de inspiración" in text and "módulo 9 no existe" in text
    assert _count(course) == 0


def test_rejects_bank_from_other_university_or_course(course):
    bank = make_bank("OTRA")
    res = _import(course, bank)
    assert not res.ok and any("universidad" in e for e in res.errors)
    bank = make_bank(_uni_code(course))
    bank["metadata"]["materia"] = "CONTABILIDAD"
    res = _import(course, bank)
    assert not res.ok and any("materia" in e for e in res.errors)


def test_dry_run_writes_nothing(course):
    res = _import(course, make_bank(_uni_code(course)), dry_run=True)
    assert res.ok and res.created == 24
    assert _count(course) == 0


def test_page_out_of_range_rejected(course):
    bank = make_bank(_uni_code(course))
    bank["questions"][0]["source_page"] = 99
    res = _import(course, bank)
    assert not res.ok and any("fuera de rango" in e for e in res.errors)


def test_other_university_cannot_see_imported_bank(course, tenant_factory):
    _import(course, make_bank(_uni_code(course)))
    other = tenant_factory()
    with db.tenant_session(other.id) as s:
        assert (
            s.scalar(
                select(func.count()).select_from(models.QuestionBank).where(models.QuestionBank.course_id == course.id)
            )
            == 0
        )
