"""Modelo de datos multi-universidad del motor de evaluación.

Nombres de tablas según INSTRUCCIONES (UDL): universities, courses, exams, question_bank,
question_options, exam_attempts, attempt_questions, attempt_answers, audit_events; más tablas de
soporte (course_modules, course_sources, administrators, administrator_courses, question_imports,
exam_questions, students, attempt_results, access_throttle).

Reglas generales:
- Toda tabla con datos de una universidad lleva ``university_id`` y queda bajo Row-Level Security
  (migración 0001). Llaves foráneas compuestas ``(id, university_id)`` impiden referencias cruzadas.
- Tiempos en UTC (``timestamptz``).
- ``question_options.is_correct`` y ``question_bank.rationale`` nunca salen en DTOs de alumno.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    pass


Base.metadata.naming_convention = NAMING_CONVENTION  # type: ignore[assignment]


def _enum(name: str, *values: str) -> Enum:
    # VARCHAR + CHECK: más fácil de evolucionar que ENUM nativo.
    return Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


ADMIN_ROLE = _enum("admin_role", "platform_admin", "university_admin", "teacher")
SOURCE_USAGE = _enum("source_usage", "question_source", "scenario_inspiration")
BLOOM = _enum("bloom_level", "recordar", "comprender", "aplicar", "analizar", "evaluar", "crear")
DIFFICULTY = _enum("difficulty", "baja", "intermedia", "alta")
QUESTION_STATUS = _enum("question_status", "draft", "reviewed", "approved", "retired")
EXAM_STATUS = _enum("exam_status", "draft", "published", "closed", "cancelled")
ATTEMPT_STATUS = _enum("attempt_status", "in_progress", "finished", "expired", "voided")
AQ_STATE = _enum("attempt_question_state", "pending", "served", "answered", "omitted", "expired")
OUTCOME = _enum("answer_outcome", "correct", "wrong", "omitted", "expired")


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def _tenant() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey("universities.id", ondelete="RESTRICT"), nullable=False, index=True
    )


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _fk(cols: list[str], table: str, **kw: Any) -> ForeignKeyConstraint:
    """FK compuesta (id, university_id) → garantiza misma universidad."""
    return ForeignKeyConstraint(cols, [f"{table}.id", f"{table}.university_id"], **kw)


def _tenant_uq(table: str) -> UniqueConstraint:
    return UniqueConstraint("id", "university_id", name=f"uq_{table}_id_tenant")


# ---------------------------------------------------------------- catálogo ---


class University(Base):
    __tablename__ = "universities"
    id: Mapped[uuid.UUID] = _pk()
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = _created()


class Course(Base):
    """Materia. ``config`` guarda parámetros por defecto para nuevos exámenes."""

    __tablename__ = "courses"
    __table_args__ = (UniqueConstraint("university_id", "code"), _tenant_uq("courses"))
    id: Mapped[uuid.UUID] = _pk()
    university_id: Mapped[uuid.UUID] = _tenant()
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = _created()


class CourseModule(Base):
    __tablename__ = "course_modules"
    __table_args__ = (
        UniqueConstraint("course_id", "module_number"),
        _tenant_uq("course_modules"),
        CheckConstraint("module_number BETWEEN 1 AND 50", name="module_number_range"),
        _fk(["course_id", "university_id"], "courses"),
    )
    id: Mapped[uuid.UUID] = _pk()
    university_id: Mapped[uuid.UUID] = _tenant()
    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    module_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)


class CourseSource(Base):
    """Material académico autorizado de una materia. El importador valida citas contra esta tabla."""

    __tablename__ = "course_sources"
    __table_args__ = (
        UniqueConstraint("course_id", "file_name"),
        _tenant_uq("course_sources"),
        CheckConstraint("page_count > 0", name="page_count_positive"),
        _fk(["course_id", "university_id"], "courses"),
    )
    id: Mapped[uuid.UUID] = _pk()
    university_id: Mapped[uuid.UUID] = _tenant()
    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    module_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    usage: Mapped[str] = mapped_column(SOURCE_USAGE, nullable=False)
    copyright_restricted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


# ------------------------------------------------------------- personas ---


class Administrator(Base):
    """Docentes y administradores. Acceso con usuario y contraseña (hash Argon2id); Entra ID opcional.
    ``university_id`` NULL solo para platform_admin."""

    __tablename__ = "administrators"
    __table_args__ = (
        CheckConstraint("(role = 'platform_admin') = (university_id IS NULL)", name="platform_admin_has_no_tenant"),
        CheckConstraint("password_hash IS NOT NULL OR entra_object_id IS NOT NULL", name="has_credential"),
        CheckConstraint("failed_logins >= 0", name="failed_logins_nonneg"),
    )
    id: Mapped[uuid.UUID] = _pk()
    university_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("universities.id"), nullable=True, index=True
    )
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    entra_object_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(ADMIN_ROLE, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    failed_logins: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()


class AdminSession(Base):
    """Sesión de docente (cookie HttpOnly). Solo se guarda el hash del token. Sin RLS: se resuelve
    antes de conocer la universidad; el acceso a datos se limita después con el contexto RLS."""

    __tablename__ = "admin_sessions"
    id: Mapped[uuid.UUID] = _pk()
    administrator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = _created()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AdministratorCourse(Base):
    __tablename__ = "administrator_courses"
    __table_args__ = (_fk(["course_id", "university_id"], "courses"),)
    administrator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="CASCADE"), primary_key=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    university_id: Mapped[uuid.UUID] = _tenant()


class Student(Base):
    """Alumno identificado por matrícula dentro de su universidad (registro libre al ingresar)."""

    __tablename__ = "students"
    __table_args__ = (UniqueConstraint("university_id", "matricula"), _tenant_uq("students"))
    id: Mapped[uuid.UUID] = _pk()
    university_id: Mapped[uuid.UUID] = _tenant()
    matricula: Mapped[str] = mapped_column(String(64), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = _created()


# --------------------------------------------------------- banco académico ---


class QuestionImport(Base):
    """Bitácora de cada archivo de banco importado (metadatos institucionales sin alterar)."""

    __tablename__ = "question_imports"
    __table_args__ = (_tenant_uq("question_imports"), _fk(["course_id", "university_id"], "courses"))
    id: Mapped[uuid.UUID] = _pk()
    university_id: Mapped[uuid.UUID] = _tenant()
    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    bank_code: Mapped[str] = mapped_column(String(64), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_count: Mapped[int] = mapped_column(Integer, nullable=False)
    new_version_count: Mapped[int] = mapped_column(Integer, nullable=False)
    unchanged_count: Mapped[int] = mapped_column(Integer, nullable=False)
    imported_by: Mapped[str] = mapped_column(String(200), nullable=False)
    imported_at: Mapped[datetime] = _created()


class QuestionBank(Base):
    """Reactivo versionado. Reimportar con cambios crea ``version`` + 1; un aprobado es inmutable."""

    __tablename__ = "question_bank"
    __table_args__ = (
        UniqueConstraint("course_id", "external_id", "version"),
        _tenant_uq("question_bank"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("source_page IS NULL OR source_page >= 1", name="source_page_positive"),
        CheckConstraint(
            "status NOT IN ('reviewed','approved') OR (reviewer IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="reviewed_requires_reviewer",
        ),
        _fk(["course_id", "university_id"], "courses"),
        _fk(["source_id", "university_id"], "course_sources"),
        _fk(["import_id", "university_id"], "question_imports"),
        Index("ix_question_bank_course_status_module", "course_id", "status", "module_number"),
        Index("ix_question_bank_course_group", "course_id", "conceptual_group"),
    )
    id: Mapped[uuid.UUID] = _pk()
    university_id: Mapped[uuid.UUID] = _tenant()
    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    import_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    bank_code: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    module_number: Mapped[int] = mapped_column(Integer, nullable=False)
    topic: Mapped[str] = mapped_column(String(200), nullable=False)
    bloom: Mapped[str] = mapped_column(BLOOM, nullable=False)
    difficulty: Mapped[str] = mapped_column(DIFFICULTY, nullable=False)
    stem: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conceptual_group: Mapped[str] = mapped_column(String(64), nullable=False)
    variant: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    case_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(QUESTION_STATUS, nullable=False, server_default=text("'draft'"))
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()


# Solo una versión vigente por reactivo.
Index(
    "uq_question_bank_one_current",
    QuestionBank.course_id,
    QuestionBank.external_id,
    unique=True,
    postgresql_where=text("is_current"),
)


class QuestionOption(Base):
    __tablename__ = "question_options"
    __table_args__ = (
        UniqueConstraint("question_id", "option_code"),
        _tenant_uq("question_options"),
        CheckConstraint("option_code IN ('A','B','C','D')", name="option_code_abcd"),
        _fk(["question_id", "university_id"], "question_bank", ondelete="CASCADE"),
        Index("uq_question_options_one_correct", "question_id", unique=True, postgresql_where=text("is_correct")),
    )
    id: Mapped[uuid.UUID] = _pk()
    university_id: Mapped[uuid.UUID] = _tenant()
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    option_code: Mapped[str] = mapped_column(String(1), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)


# ------------------------------------------------------------------ exámenes ---


class Exam(Base):
    """Examen (p. ej. Parcial 1) de una materia con fecha, código de acceso y reglas congeladas.

    ``access_code_lookup`` = HMAC-SHA256(pepper, código normalizado): permite ubicar el examen por
    código sin guardar el código en claro.
    """

    __tablename__ = "exams"
    __table_args__ = (
        UniqueConstraint("course_id", "code"),
        _tenant_uq("exams"),
        CheckConstraint("ends_at > starts_at", name="window_valid"),
        CheckConstraint("status <> 'published' OR access_code_lookup IS NOT NULL", name="published_has_code"),
        _fk(["course_id", "university_id"], "courses"),
    )
    id: Mapped[uuid.UUID] = _pk()
    university_id: Mapped[uuid.UUID] = _tenant()
    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(EXAM_STATUS, nullable=False, server_default=text("'draft'"))
    access_code_lookup: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    config_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = _created()


class ExamQuestion(Base):
    """Pool congelado al publicar: versiones exactas de los reactivos aprobados (regla 6)."""

    __tablename__ = "exam_questions"
    __table_args__ = (
        _fk(["exam_id", "university_id"], "exams"),
        _fk(["question_id", "university_id"], "question_bank"),
    )
    exam_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    university_id: Mapped[uuid.UUID] = _tenant()


# ----------------------------------------------------------------- intentos ---


class ExamAttempt(Base):
    """Intento. Unicidad (examen, alumno, n.º) impide reintentos sin autorización auditada."""

    __tablename__ = "exam_attempts"
    __table_args__ = (
        UniqueConstraint("exam_id", "student_id", "attempt_number"),
        _tenant_uq("exam_attempts"),
        CheckConstraint("attempt_number >= 1", name="attempt_number_positive"),
        _fk(["exam_id", "university_id"], "exams"),
        _fk(["student_id", "university_id"], "students"),
        Index("ix_exam_attempts_exam_status", "exam_id", "status"),
    )
    id: Mapped[uuid.UUID] = _pk()
    university_id: Mapped[uuid.UUID] = _tenant()
    exam_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    full_name_entered: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(ATTEMPT_STATUS, nullable=False, server_default=text("'in_progress'"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    window_deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_ordinal: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    seed: Mapped[str] = mapped_column(String(128), nullable=False)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))


class AttemptQuestion(Base):
    """Selección inmutable del intento, con orden de opciones y deadline del servidor."""

    __tablename__ = "attempt_questions"
    __table_args__ = (
        UniqueConstraint("attempt_id", "question_id"),
        CheckConstraint("ordinal >= 1", name="ordinal_positive"),
        CheckConstraint("deadline_at IS NULL OR served_at IS NOT NULL", name="deadline_requires_served"),
        _fk(["attempt_id", "university_id"], "exam_attempts", ondelete="CASCADE"),
        _fk(["question_id", "university_id"], "question_bank"),
        Index("ix_attempt_questions_question", "question_id"),
    )
    attempt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    university_id: Mapped[uuid.UUID] = _tenant()
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    module_number: Mapped[int] = mapped_column(Integer, nullable=False)
    options_order: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    served_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    state: Mapped[str] = mapped_column(AQ_STATE, nullable=False, server_default=text("'pending'"))


class AttemptAnswer(Base):
    """Una respuesta por (intento, ordinal); ``idempotency_key`` vuelve seguros los reintentos de red."""

    __tablename__ = "attempt_answers"
    __table_args__ = (
        UniqueConstraint("attempt_id", "ordinal"),
        UniqueConstraint("attempt_id", "idempotency_key"),
        CheckConstraint(
            "(outcome IN ('correct','wrong')) = (selected_option_id IS NOT NULL)", name="selection_matches_outcome"
        ),
        ForeignKeyConstraint(
            ["attempt_id", "ordinal"],
            ["attempt_questions.attempt_id", "attempt_questions.ordinal"],
            ondelete="CASCADE",
        ),
        _fk(["selected_option_id", "university_id"], "question_options"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    university_id: Mapped[uuid.UUID] = _tenant()
    attempt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    selected_option_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    outcome: Mapped[str] = mapped_column(OUTCOME, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AttemptResult(Base):
    __tablename__ = "attempt_results"
    __table_args__ = (
        CheckConstraint("correct >= 0 AND wrong >= 0 AND omitted >= 0 AND expired >= 0", name="counts_nonneg"),
        CheckConstraint("correct + wrong + omitted + expired = total", name="counts_sum_total"),
        CheckConstraint("grade >= 0 AND grade <= 100", name="grade_range"),
        _fk(["attempt_id", "university_id"], "exam_attempts"),
    )
    attempt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    university_id: Mapped[uuid.UUID] = _tenant()
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    correct: Mapped[int] = mapped_column(Integer, nullable=False)
    wrong: Mapped[int] = mapped_column(Integer, nullable=False)
    omitted: Mapped[int] = mapped_column(Integer, nullable=False)
    expired: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_score: Mapped[int] = mapped_column(Integer, nullable=False)
    grade: Mapped[float] = mapped_column(Numeric(7, 4), nullable=False)
    scoring_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    computed_at: Mapped[datetime] = _created()


class AuditEvent(Base):
    """Bitácora append-only (sin claves ni secretos en ``metadata``)."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_attempt", "attempt_id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    university_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("universities.id"), nullable=True, index=True
    )
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = _created()
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class AccessThrottle(Base):
    """Contador de intentos de ingreso por clave (IP o matrícula) y ventana; sin RLS (previo al tenant)."""

    __tablename__ = "access_throttle"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


TENANT_TABLES: tuple[str, ...] = (
    "courses",
    "course_modules",
    "course_sources",
    "administrator_courses",
    "students",
    "question_imports",
    "question_bank",
    "question_options",
    "exams",
    "exam_questions",
    "exam_attempts",
    "attempt_questions",
    "attempt_answers",
    "attempt_results",
)
NULLABLE_TENANT_TABLES: tuple[str, ...] = ("administrators", "audit_events")
