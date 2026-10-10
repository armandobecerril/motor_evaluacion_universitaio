"""Fixtures de integración contra PostgreSQL real.

Requiere:
- TEST_MIGRATION_DATABASE_URL: rol propietario sobre una BD de pruebas DESECHABLE.
- TEST_DATABASE_URL: rol ``exam_app`` (sin privilegios de propietario) sobre la misma BD.
La BD se reconstruye (downgrade base + upgrade head) al inicio de la sesión de pruebas.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from exam_engine import db, models
from exam_engine.config import get_settings

API_DIR = Path(__file__).resolve().parents[1]


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} no definida: se omiten pruebas de integración", allow_module_level=True)
    return value


@pytest.fixture(scope="session")
def alembic_cfg() -> Config:
    owner_url = _require("TEST_MIGRATION_DATABASE_URL")
    os.environ["MIGRATION_DATABASE_URL"] = owner_url
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    return cfg


@pytest.fixture(scope="session", autouse=True)
def migrated_db(alembic_cfg: Config) -> Iterator[None]:
    app_url = _require("TEST_DATABASE_URL")
    os.environ["DATABASE_URL"] = app_url
    get_settings.cache_clear()
    db.reset_engine()
    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")
    yield
    db.reset_engine()


class Tenant:
    """Grafo mínimo de una universidad: materia SIAF, 1 módulo, 1 fuente, 1 alumno, 1 convocatoria."""

    def __init__(self, code: str) -> None:
        self.code = code
        with db.tenant_session(None, platform_admin=True) as s:
            inst = models.Institution(code=code, name=f"Universidad {code}")
            s.add(inst)
            s.flush()
            self.id = inst.id
            subj = models.Subject(
                institution_id=inst.id, code="SIAF", name="Sistemas Informáticos Aplicados a Finanzas"
            )
            s.add(subj)
            s.flush()
            self.subject_id = subj.id
            mod = models.SubjectModule(
                institution_id=inst.id, subject_id=subj.id, module_number=1, name="M1", bank_target=120
            )
            s.add(mod)
            s.flush()
            self.module_id = mod.id
            src = models.SubjectSource(
                institution_id=inst.id,
                subject_id=subj.id,
                module_id=mod.id,
                file_name="01_demo.pdf",
                page_count=15,
                usage="question_source",
            )
            stu = models.Student(institution_id=inst.id, matricula="A001", full_name="Alumno Demo")
            s.add_all([src, stu])
            s.flush()
            self.source_id, self.student_id = src.id, stu.id
            now = datetime.now(UTC)
            ev = models.ExamVersion(
                institution_id=inst.id,
                subject_id=subj.id,
                code="A",
                name="Convocatoria A",
                starts_at=now,
                ends_at=now + timedelta(hours=2),
                config={"exam_size": 200, "seconds_per_question": 20},
            )
            s.add(ev)
            s.flush()
            self.exam_version_id = ev.id

    def new_question(self, s, *, status: str = "draft", external_id: str | None = None) -> models.Question:
        q = models.Question(
            institution_id=self.id,
            subject_id=self.subject_id,
            module_id=self.module_id,
            external_id=external_id or f"T-{uuid.uuid4().hex[:8]}",
            topic="Demo",
            bloom="aplicar",
            difficulty="media",
            stem="Enunciado de prueba",
            rationale="Justificación",
            source_id=self.source_id,
            source_page=3,
            conceptual_group="DEMO",
            status=status,
            checksum="0" * 64,
            author="pytest",
        )
        s.add(q)
        s.flush()
        return q

    def add_options(self, s, q: models.Question, correct: str | None = "B", codes: str = "ABCD") -> None:
        for c in codes:
            s.add(
                models.QuestionOption(
                    institution_id=self.id,
                    question_id=q.id,
                    option_code=c,
                    text=f"Opción {c}",
                    is_correct=(c == correct),
                )
            )
        s.flush()


@pytest.fixture()
def tenant_factory() -> Iterator:
    def make() -> Tenant:
        return Tenant(f"U{uuid.uuid4().hex[:6].upper()}")

    yield make
