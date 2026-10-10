"""Importación idempotente del banco a PostgreSQL.

- Todo o nada: si hay un solo error de validación, no se escribe nada.
- Idempotente por ``id`` (external_id): mismo contenido → sin cambios; contenido distinto → nueva versión
  (la anterior deja de ser vigente y se conserva). Cada cambio queda en ``audit_events``.
- Todo reactivo entra como ``draft``: la aprobación es exclusivamente docente.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import models
from .bank_format import CourseContext, ParsedBank, parse_bank, validate_against_course


@dataclass
class ImportResult:
    ok: bool
    dry_run: bool
    bank_code: str
    total: int = 0
    created: int = 0
    new_versions: int = 0
    unchanged: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    import_id: uuid.UUID | None = None
    group_changes: list[str] = field(default_factory=list)


def course_context(s: Session, course: models.Course) -> CourseContext:
    uni = s.get(models.University, course.university_id)
    assert uni is not None
    modules = s.scalars(select(models.CourseModule.module_number).where(models.CourseModule.course_id == course.id))
    sources = s.scalars(select(models.CourseSource).where(models.CourseSource.course_id == course.id))
    return CourseContext(
        university_code=uni.code,
        course_name=course.name,
        module_numbers=frozenset(modules),
        sources={src.file_name: (src.page_count, src.usage, src.module_number) for src in sources},
    )


def parse_and_validate(s: Session, course: models.Course, data: bytes, file_name: str) -> ParsedBank:
    bank = parse_bank(data, file_name)
    validate_against_course(bank, course_context(s, course))
    return bank


def import_bank(
    s: Session,
    course: models.Course,
    data: bytes,
    file_name: str,
    *,
    actor: str,
    dry_run: bool = False,
) -> ImportResult:
    bank = parse_and_validate(s, course, data, file_name)
    code = bank.bank_code or f"{course.code}-{file_name.rsplit('.', 1)[0]}"[:64]
    res = ImportResult(ok=not bank.errors, dry_run=dry_run, bank_code=code, total=len(bank.items))
    res.errors, res.warnings = bank.errors[:200], bank.warnings
    if bank.errors:
        return res

    sources = {
        src.file_name: src.id
        for src in s.scalars(select(models.CourseSource).where(models.CourseSource.course_id == course.id))
    }
    current = {
        q.external_id: q
        for q in s.scalars(
            select(models.QuestionBank).where(
                models.QuestionBank.course_id == course.id, models.QuestionBank.is_current.is_(True)
            )
        )
    }
    plan: list[tuple[str, object]] = []
    for it in bank.items:
        prev = current.get(it.external_id)
        if prev is None:
            res.created += 1
            plan.append(("create", it))
        elif prev.checksum == it.checksum():
            res.unchanged += 1
        else:
            res.new_versions += 1
            if prev.conceptual_group != it.conceptual_group:
                res.group_changes.append(f"{it.external_id}: {prev.conceptual_group} → {it.conceptual_group}")
            plan.append(("version", (prev, it)))
    if dry_run:
        return res

    imp = models.QuestionImport(
        university_id=course.university_id,
        course_id=course.id,
        bank_code=code,
        file_name=file_name[:255],
        file_sha256=hashlib.sha256(data).hexdigest(),
        source_metadata=bank.metadata,  # se conserva sin alterar
        created_count=res.created,
        new_version_count=res.new_versions,
        unchanged_count=res.unchanged,
        imported_by=actor,
    )
    s.add(imp)
    s.flush()
    res.import_id = imp.id

    def insert(it, version: int) -> models.QuestionBank:  # type: ignore[no-untyped-def]
        q = models.QuestionBank(
            university_id=course.university_id,
            course_id=course.id,
            import_id=imp.id,
            bank_code=code,
            external_id=it.external_id,
            version=version,
            is_current=True,
            module_number=it.module_number,
            topic=it.topic,
            bloom=it.bloom,
            difficulty=it.difficulty,
            stem=it.stem,
            rationale=it.rationale,
            source_id=sources[it.source_pdf],
            source_page=it.source_page,
            conceptual_group=it.conceptual_group,
            variant=it.variant,
            case_type=it.case_type,
            status="draft",
            checksum=it.checksum(),
        )
        s.add(q)
        s.flush()
        s.add_all(
            models.QuestionOption(
                university_id=course.university_id,
                question_id=q.id,
                option_code=code_,
                text=text_,
                is_correct=(code_ == it.correct_option),
            )
            for code_, text_ in sorted(it.options.items())
        )
        return q

    for kind, payload in plan:
        if kind == "create":
            insert(payload, 1)
        else:
            prev, it = payload  # type: ignore[misc]
            s.execute(update(models.QuestionBank).where(models.QuestionBank.id == prev.id).values(is_current=False))
            s.flush()
            q = insert(it, prev.version + 1)
            s.add(
                models.AuditEvent(
                    university_id=course.university_id,
                    actor_type="admin",
                    actor_id=actor,
                    event_type="question.new_version",
                    event_metadata={
                        "external_id": it.external_id,
                        "from_version": prev.version,
                        "to_version": q.version,
                        "previous_status": prev.status,
                        "conceptual_group_changed": prev.conceptual_group != it.conceptual_group,
                    },
                )
            )
    s.add(
        models.AuditEvent(
            university_id=course.university_id,
            actor_type="admin",
            actor_id=actor,
            event_type="bank.imported",
            event_metadata={
                "import_id": str(imp.id),
                "bank_code": code,
                "file_sha256": imp.file_sha256,
                "created": res.created,
                "new_versions": res.new_versions,
                "unchanged": res.unchanged,
            },
        )
    )
    s.flush()
    return res
