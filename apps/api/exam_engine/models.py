"""Modelo de datos multi-universidad del motor de evaluación (ADR-001, ADR-003).

Reglas generales:
- Toda tabla con datos de una universidad lleva ``institution_id`` y queda bajo
  Row-Level Security (ver migración 0001). La tabla ``institutions`` no.
- Tiempos en UTC (``timestamptz``).
- Las claves de respuesta (``question_options.is_correct``) y ``questions.rationale``
  nunca se exponen en DTOs de estudiante.
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
    # Enums como VARCHAR + CHECK: más fáciles de evolucionar con migraciones.
    return Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


ADMIN_ROLE = _enum("admin_role", "platform_admin", "institution_admin", "teacher")
SOURCE_USAGE = _enum("source_usage", "question_source", "scenario_inspiration")
BLOOM = _enum("bloom_level", "recordar", "comprender", "aplicar", "analizar", "evaluar", "crear")
DIFFICULTY = _enum("difficulty", "baja", "media", "alta")
QUESTION_STATUS = _enum("question_status", "draft", "reviewed", "approved", "retired")
SESSION_STATUS = _enum("session_status", "in_progress", "finished", "expired", "voided")
SQ_STATE = _enum("session_question_state", "pending", "served", "answered", "omitted", "expired")
OUTCOME = _enum("answer_outcome", "correct", "wrong", "omitted", "expired")


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def _tenant() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=False, index=True
    )


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


# ---------------------------------------------------------------- catálogo ---


class Institution(Base):
    __tablename__ = "institutions"
    id: Mapped[uuid.UUID] = _pk()
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = _created()


class Subject(Base):
    """Materia. ``config`` guarda parámetros por defecto (módulos, tamaño de examen, scoring...)."""

    __tablename__ = "subjects"
    __table_args__ = (
        UniqueConstraint("institution_id", "code"),
        UniqueConstraint("id", "institution_id", name="uq_subjects_id_tenant"),
    )
    id: Mapped[uuid.UUID] = _pk()
    institution_id: Mapped[uuid.UUID] = _tenant()
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = _created()


class SubjectModule(Base):
    __tablename__ = "subject_modules"
    __table_args__ = (
        UniqueConstraint("subject_id", "module_number"),
        UniqueConstraint("id", "institution_id", name="uq_subject_modules_id_tenant"),
        CheckConstraint("module_number BETWEEN 1 AND 50", name="module_number_range"),
        CheckConstraint("bank_target >= 0", name="bank_target_nonneg"),
        ForeignKeyConstraint(["subject_id", "institution_id"], ["subjects.id", "subjects.institution_id"]),
    )
    id: Mapped[uuid.UUID] = _pk()
    institution_id: Mapped[uuid.UUID] = _tenant()
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    module_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    bank_target: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class SubjectSource(Base):
    """Material académico autorizado (PDF) de una materia. El importador valida citas contra esta tabla."""

    __tablename__ = "subject_sources"
    __table_args__ = (
        UniqueConstraint("subject_id", "file_name"),
        UniqueConstraint("id", "institution_id", name="uq_subject_sources_id_tenant"),
        CheckConstraint("page_count > 0", name="page_count_positive"),
        ForeignKeyConstraint(["subject_id", "institution_id"], ["subjects.id", "subjects.institution_id"]),
    )
    id: Mapped[uuid.UUID] = _pk()
    institution_id: Mapped[uuid.UUID] = _tenant()
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    module_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subject_modules.id"), nullable=True
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    usage: Mapped[str] = mapped_column(SOURCE_USAGE, nullable=False)
    copyright_restricted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


# ------------------------------------------------------------- personas ---


class Administrator(Base):
    """Docentes y administradores (Entra ID). ``institution_id`` NULL solo para platform_admin."""

    __tablename__ = "administrators"
    __table_args__ = (
        CheckConstraint("(role = 'platform_admin') = (institution_id IS NULL)", name="platform_admin_has_no_tenant"),
    )
    id: Mapped[uuid.UUID] = _pk()
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("institutions.id"), nullable=True, index=True
    )
    entra_object_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(ADMIN_ROLE, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = _created()


class AdministratorSubject(Base):
    """Alcance de un docente: materias que puede ver/administrar."""

    __tablename__ = "administrator_subjects"
    __table_args__ = (
        ForeignKeyConstraint(["subject_id", "institution_id"], ["subjects.id", "subjects.institution_id"]),
    )
    administrator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("administrators.id", ondelete="CASCADE"), primary_key=True
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    institution_id: Mapped[uuid.UUID] = _tenant()


class Student(Base):
    __tablename__ = "students"
    __table_args__ = (
        UniqueConstraint("institution_id", "matricula"),
        UniqueConstraint("id", "institution_id", name="uq_students_id_tenant"),
    )
    id: Mapped[uuid.UUID] = _pk()
    institution_id: Mapped[uuid.UUID] = _tenant()
    matricula: Mapped[str] = mapped_column(String(64), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    group_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = _created()


# --------------------------------------------------------- banco académico ---


class Question(Base):
    """Reactivo versionado. Una corrección crea una nueva ``version``; nunca se edita una aprobada."""

    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("subject_id", "external_id", "version"),
        UniqueConstraint("id", "institution_id", name="uq_questions_id_tenant"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("source_page >= 1", name="source_page_positive"),
        CheckConstraint(
            "status NOT IN ('reviewed','approved') OR (reviewer IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="reviewed_requires_reviewer",
        ),
        ForeignKeyConstraint(["subject_id", "institution_id"], ["subjects.id", "subjects.institution_id"]),
        ForeignKeyConstraint(["module_id", "institution_id"], ["subject_modules.id", "subject_modules.institution_id"]),
        ForeignKeyConstraint(["source_id", "institution_id"], ["subject_sources.id", "subject_sources.institution_id"]),
        Index("ix_questions_subject_status_module", "subject_id", "status", "module_id"),
    )
    id: Mapped[uuid.UUID] = _pk()
    institution_id: Mapped[uuid.UUID] = _tenant()
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    module_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    topic: Mapped[str] = mapped_column(String(200), nullable=False)
    bloom: Mapped[str] = mapped_column(BLOOM, nullable=False)
    difficulty: Mapped[str] = mapped_column(DIFFICULTY, nullable=False)
    stem: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_page: Mapped[int] = mapped_column(Integer, nullable=False)
    conceptual_group: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(QUESTION_STATUS, nullable=False, server_default=text("'draft'"))
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    author: Mapped[str] = mapped_column(String(200), nullable=False)
    reviewer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()


class QuestionOption(Base):
    __tablename__ = "question_options"
    __table_args__ = (
        UniqueConstraint("question_id", "option_code"),
        UniqueConstraint("id", "institution_id", name="uq_question_options_id_tenant"),
        CheckConstraint("option_code IN ('A','B','C','D')", name="option_code_abcd"),
        ForeignKeyConstraint(
            ["question_id", "institution_id"],
            ["questions.id", "questions.institution_id"],
            ondelete="CASCADE",
        ),
        # A lo sumo una correcta por reactivo; "exactamente una y 4 opciones" lo valida el importador
        # y el trigger de aprobación (migración 0001).
        Index(
            "uq_question_options_one_correct",
            "question_id",
            unique=True,
            postgresql_where=text("is_correct"),
        ),
    )
    id: Mapped[uuid.UUID] = _pk()
    institution_id: Mapped[uuid.UUID] = _tenant()
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    option_code: Mapped[str] = mapped_column(String(1), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)


class BankPublication(Base):
    """Versión congelada del banco aprobado de una materia (regla 6 del ADR-001)."""

    __tablename__ = "bank_publications"
    __table_args__ = (
        UniqueConstraint("subject_id", "version"),
        UniqueConstraint("id", "institution_id", name="uq_bank_publications_id_tenant"),
        ForeignKeyConstraint(["subject_id", "institution_id"], ["subjects.id", "subjects.institution_id"]),
    )
    id: Mapped[uuid.UUID] = _pk()
    institution_id: Mapped[uuid.UUID] = _tenant()
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    published_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("administrators.id"), nullable=False)
    published_at: Mapped[datetime] = _created()


class BankPublicationQuestion(Base):
    __tablename__ = "bank_publication_questions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["publication_id", "institution_id"], ["bank_publications.id", "bank_publications.institution_id"]
        ),
        ForeignKeyConstraint(["question_id", "institution_id"], ["questions.id", "questions.institution_id"]),
    )
    publication_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    institution_id: Mapped[uuid.UUID] = _tenant()


# ------------------------------------------------------------ convocatorias ---


class ExamVersion(Base):
    """Convocatoria (p. ej. A/B). ``config`` = parámetros congelados al abrir: tamaño, cuotas, tiempo,
    scoring, ventana y tolerancia de red. ``access_code_hash`` nunca guarda el código en claro."""

    __tablename__ = "exam_versions"
    __table_args__ = (
        UniqueConstraint("subject_id", "code"),
        UniqueConstraint("id", "institution_id", name="uq_exam_versions_id_tenant"),
        CheckConstraint("ends_at > starts_at", name="window_valid"),
        ForeignKeyConstraint(["subject_id", "institution_id"], ["subjects.id", "subjects.institution_id"]),
        ForeignKeyConstraint(
            ["publication_id", "institution_id"], ["bank_publications.id", "bank_publications.institution_id"]
        ),
    )
    id: Mapped[uuid.UUID] = _pk()
    institution_id: Mapped[uuid.UUID] = _tenant()
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    publication_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    access_code_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    config_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_at: Mapped[datetime] = _created()


class ExamVersionPool(Base):
    __tablename__ = "exam_version_pool"
    __table_args__ = (
        ForeignKeyConstraint(
            ["exam_version_id", "institution_id"], ["exam_versions.id", "exam_versions.institution_id"]
        ),
        ForeignKeyConstraint(["question_id", "institution_id"], ["questions.id", "questions.institution_id"]),
    )
    exam_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    institution_id: Mapped[uuid.UUID] = _tenant()
    allocation_tag: Mapped[str | None] = mapped_column(String(32), nullable=True)


class ExamVersionRoster(Base):
    """Matrículas autorizadas en una convocatoria (control de acceso de ADR-004)."""

    __tablename__ = "exam_version_roster"
    __table_args__ = (
        CheckConstraint("allowed_attempts >= 1", name="allowed_attempts_positive"),
        ForeignKeyConstraint(
            ["exam_version_id", "institution_id"], ["exam_versions.id", "exam_versions.institution_id"]
        ),
        ForeignKeyConstraint(["student_id", "institution_id"], ["students.id", "students.institution_id"]),
    )
    exam_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    institution_id: Mapped[uuid.UUID] = _tenant()
    allowed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))


# ----------------------------------------------------------------- intentos ---


class ExamSession(Base):
    """Intento de un alumno. Unicidad (convocatoria, alumno, n.º intento) impide reintentos no autorizados."""

    __tablename__ = "exam_sessions"
    __table_args__ = (
        UniqueConstraint("exam_version_id", "student_id", "attempt_number"),
        UniqueConstraint("id", "institution_id", name="uq_exam_sessions_id_tenant"),
        CheckConstraint("attempt_number >= 1", name="attempt_number_positive"),
        ForeignKeyConstraint(
            ["exam_version_id", "institution_id"], ["exam_versions.id", "exam_versions.institution_id"]
        ),
        ForeignKeyConstraint(["student_id", "institution_id"], ["students.id", "students.institution_id"]),
        Index("ix_exam_sessions_version_status", "exam_version_id", "status"),
    )
    id: Mapped[uuid.UUID] = _pk()
    institution_id: Mapped[uuid.UUID] = _tenant()
    exam_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    status: Mapped[str] = mapped_column(SESSION_STATUS, nullable=False, server_default=text("'in_progress'"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    window_deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_ordinal: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    seed: Mapped[str] = mapped_column(String(128), nullable=False)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))


class ExamSessionQuestion(Base):
    """Selección inmutable de preguntas del intento, con orden de opciones y deadline del servidor."""

    __tablename__ = "exam_session_questions"
    __table_args__ = (
        UniqueConstraint("session_id", "question_id"),
        CheckConstraint("ordinal >= 1", name="ordinal_positive"),
        CheckConstraint("deadline_at IS NULL OR served_at IS NOT NULL", name="deadline_requires_served"),
        ForeignKeyConstraint(
            ["session_id", "institution_id"],
            ["exam_sessions.id", "exam_sessions.institution_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(["question_id", "institution_id"], ["questions.id", "questions.institution_id"]),
        Index("ix_exam_session_questions_question", "question_id"),
    )
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    institution_id: Mapped[uuid.UUID] = _tenant()
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    module_number: Mapped[int] = mapped_column(Integer, nullable=False)
    options_order: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    served_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    state: Mapped[str] = mapped_column(SQ_STATE, nullable=False, server_default=text("'pending'"))


class Answer(Base):
    """Una respuesta por (intento, ordinal). ``idempotency_key`` hace seguros los reintentos de red."""

    __tablename__ = "answers"
    __table_args__ = (
        UniqueConstraint("session_id", "ordinal"),
        UniqueConstraint("session_id", "idempotency_key"),
        CheckConstraint(
            "(outcome IN ('correct','wrong')) = (selected_option_id IS NOT NULL)",
            name="selection_matches_outcome",
        ),
        ForeignKeyConstraint(
            ["session_id", "ordinal"],
            ["exam_session_questions.session_id", "exam_session_questions.ordinal"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["selected_option_id", "institution_id"],
            ["question_options.id", "question_options.institution_id"],
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    institution_id: Mapped[uuid.UUID] = _tenant()
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    selected_option_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    outcome: Mapped[str] = mapped_column(OUTCOME, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ExamResult(Base):
    __tablename__ = "exam_results"
    __table_args__ = (
        CheckConstraint("correct >= 0 AND wrong >= 0 AND omitted >= 0 AND expired >= 0", name="counts_nonneg"),
        CheckConstraint("correct + wrong + omitted + expired = total", name="counts_sum_total"),
        CheckConstraint("grade >= 0 AND grade <= 100", name="grade_range"),
        ForeignKeyConstraint(["session_id", "institution_id"], ["exam_sessions.id", "exam_sessions.institution_id"]),
    )
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    institution_id: Mapped[uuid.UUID] = _tenant()
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
    __table_args__ = (Index("ix_audit_events_session", "session_id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("institutions.id"), nullable=True, index=True
    )
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = _created()
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


# Tablas sujetas a Row-Level Security (todas salvo institutions; administrators y audit_events
# tienen política especial porque admiten institution_id NULL).
TENANT_TABLES: tuple[str, ...] = (
    "subjects",
    "subject_modules",
    "subject_sources",
    "administrator_subjects",
    "students",
    "questions",
    "question_options",
    "bank_publications",
    "bank_publication_questions",
    "exam_versions",
    "exam_version_pool",
    "exam_version_roster",
    "exam_sessions",
    "exam_session_questions",
    "answers",
    "exam_results",
)
NULLABLE_TENANT_TABLES: tuple[str, ...] = ("administrators", "audit_events")
