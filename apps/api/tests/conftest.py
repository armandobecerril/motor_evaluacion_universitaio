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
os.environ.setdefault("ACCESS_CODE_PEPPER", "pepper-solo-para-pruebas")
os.environ.setdefault("APP_ENV", "local")


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
    """Grafo mínimo de una universidad: materia SIAF, 1 módulo, 1 fuente, 1 alumno, 1 examen."""

    def __init__(self, code: str) -> None:
        self.code = code
        with db.tenant_session(None, platform_admin=True) as s:
            inst = models.University(code=code, name=f"Universidad {code}")
            s.add(inst)
            s.flush()
            self.id = inst.id
            subj = models.Course(university_id=inst.id, code="SIAF", name="Sistemas Informáticos Aplicados a Finanzas")
            s.add(subj)
            s.flush()
            self.course_id = subj.id
            s.add(models.CourseModule(university_id=inst.id, course_id=subj.id, module_number=1, name="M1"))
            src = models.CourseSource(
                university_id=inst.id,
                course_id=subj.id,
                module_number=1,
                file_name="01_demo.pdf",
                page_count=15,
                usage="question_source",
            )
            stu = models.Student(university_id=inst.id, matricula="A001", full_name="Alumno Demo")
            s.add_all([src, stu])
            s.flush()
            self.source_id, self.student_id = src.id, stu.id
            imp = models.QuestionImport(
                university_id=inst.id,
                course_id=subj.id,
                bank_code="TEST",
                file_name="test.json",
                file_sha256="0" * 64,
                source_metadata={},
                created_count=0,
                new_version_count=0,
                unchanged_count=0,
                imported_by="pytest",
            )
            s.add(imp)
            s.flush()
            self.import_id = imp.id
            now = datetime.now(UTC)
            ev = models.Exam(
                university_id=inst.id,
                course_id=subj.id,
                code="PARCIAL-1",
                name="Parcial 1",
                starts_at=now,
                ends_at=now + timedelta(hours=2),
                config={"exam_size": 200, "seconds_per_question": 20},
            )
            s.add(ev)
            s.flush()
            self.exam_id = ev.id

    def new_question(self, s, *, status: str = "draft", external_id: str | None = None) -> models.QuestionBank:
        q = models.QuestionBank(
            university_id=self.id,
            course_id=self.course_id,
            import_id=self.import_id,
            bank_code="TEST",
            module_number=1,
            external_id=external_id or f"T-{uuid.uuid4().hex[:8]}",
            topic="Demo",
            bloom="aplicar",
            difficulty="intermedia",
            stem="Enunciado de prueba",
            rationale="Justificación",
            source_id=self.source_id,
            source_page=3,
            conceptual_group="DEMO",
            status=status,
            checksum="0" * 64,
        )
        s.add(q)
        s.flush()
        return q

    def add_options(self, s, q: models.QuestionBank, correct: str | None = "B", codes: str = "ABCD") -> None:
        for c in codes:
            s.add(
                models.QuestionOption(
                    university_id=self.id,
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


# ------------------------------------------------------------ materia UDL/SIAF ---

SEED_FILE = API_DIR / "seeds" / "udl_siaf_catalog.json"


@pytest.fixture()
def course(tmp_path) -> models.Course:
    """Materia SIAF sembrada en una universidad nueva (código aleatorio) para aislar cada prueba."""
    import json

    from sqlalchemy import select

    from exam_engine.seeding import seed_catalog

    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    code = f"U{uuid.uuid4().hex[:6].upper()}"
    data["university"] = {"code": code, "name": code}
    f = tmp_path / "seed.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    seed_catalog(f)
    with db.tenant_session(None, platform_admin=True) as s:
        uni = s.scalar(select(models.University).where(models.University.code == code))
        return s.scalar(select(models.Course).where(models.Course.university_id == uni.id))


def make_bank(university: str, *, groups_per_module: int = 3, variants: int = 2, **overrides) -> dict:
    """Banco sintético en formato UDL v2 (concept_id, source_page nulo)."""
    pdfs = {
        1: "01_Sistemas-de-Informacion-en-la-Funcion-Financiera.pdf",
        2: "02_Arquitectura-Empresarial.pdf",
        3: "03_El-ERP.pdf",
        4: "04_AUTOMATIZACION-FINANCIERA.pdf",
    }
    qs = []
    n = 0
    for m in range(1, 5):
        for g in range(1, groups_per_module + 1):
            for v in range(1, variants + 1):
                n += 1
                qs.append(
                    {
                        "id": f"T-{n:04d}",
                        "universidad": university,
                        "materia": "SISTEMAS INFORMÁTICOS APLICADOS A FINANZAS",
                        "examen": "Parcial 1",
                        "module": m,
                        "topic": f"Tema {m}.{g}",
                        "bloom": "Analizar",
                        "difficulty": "intermedia",
                        "stem": f"Caso {n}: una empresa del sector {v} enfrenta la situación {g} del módulo {m}. ¿Qué conviene?",
                        "options": [{"id": c, "text": f"Opción {c} del caso {n}"} for c in "ABCD"],
                        "correct_option_id": "ABCD"[n % 4],
                        "rationale": f"Justificación {n}",
                        "source_pdf": pdfs[m],
                        "source_page": None,
                        "case_type": "diagnóstico",
                        "concept_id": f"M{m:02d}-C{g:02d}",
                        "status": "ready_for_professor_review",
                    }
                )
    bank = {
        "metadata": {
            "id": "TEST-BANK",
            "universidad": university,
            "materia": "SISTEMAS INFORMÁTICOS APLICADOS A FINANZAS",
            "examen": "Parcial 1",
        },
        "questions": qs,
    }
    bank.update(overrides)
    return bank
