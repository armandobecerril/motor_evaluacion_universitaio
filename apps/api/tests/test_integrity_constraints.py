"""Restricciones críticas del ADR-001 aplicadas por la base de datos."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from exam_engine import db, models


def _approve(s, q):
    s.execute(
        update(models.QuestionBank)
        .where(models.QuestionBank.id == q.id)
        .values(status="approved", reviewer="Docente", reviewed_at=datetime.now(UTC))
    )
    s.flush()


# ------------------------------------------------------------------ banco ---


def test_only_one_correct_option(tenant_factory):
    t = tenant_factory()
    with pytest.raises(IntegrityError):
        with db.tenant_session(t.id) as s:
            q = t.new_question(s)
            s.add_all(
                [
                    models.QuestionOption(university_id=t.id, question_id=q.id, option_code=c, text=c, is_correct=True)
                    for c in "AB"
                ]
            )
            s.flush()


def test_option_codes_restricted(tenant_factory):
    t = tenant_factory()
    with pytest.raises(IntegrityError):
        with db.tenant_session(t.id) as s:
            q = t.new_question(s)
            s.add(
                models.QuestionOption(university_id=t.id, question_id=q.id, option_code="E", text="x", is_correct=False)
            )
            s.flush()


@pytest.mark.parametrize(("codes", "correct"), [("ABC", "B"), ("ABCD", None)])
def test_approval_requires_four_options_and_one_correct(tenant_factory, codes, correct):
    t = tenant_factory()
    with pytest.raises(DBAPIError, match="4 opciones y 1 correcta"):
        with db.tenant_session(t.id) as s:
            q = t.new_question(s)
            t.add_options(s, q, correct=correct, codes=codes)
            _approve(s, q)


def test_approval_requires_reviewer(tenant_factory):
    t = tenant_factory()
    with pytest.raises(IntegrityError):
        with db.tenant_session(t.id) as s:
            q = t.new_question(s)
            t.add_options(s, q)
            s.execute(update(models.QuestionBank).where(models.QuestionBank.id == q.id).values(status="approved"))
            s.flush()


def test_valid_question_can_be_approved_and_then_is_immutable(tenant_factory):
    t = tenant_factory()
    with db.tenant_session(t.id) as s:
        q = t.new_question(s)
        t.add_options(s, q)
        _approve(s, q)
        qid = q.id
    with pytest.raises(DBAPIError, match="inmutable"):
        with db.tenant_session(t.id) as s:
            s.execute(update(models.QuestionBank).where(models.QuestionBank.id == qid).values(stem="cambiado"))
    with pytest.raises(DBAPIError, match="inmutables"):
        with db.tenant_session(t.id) as s:
            s.execute(
                update(models.QuestionOption).where(models.QuestionOption.question_id == qid).values(is_correct=False)
            )
    # Retirar sí está permitido.
    with db.tenant_session(t.id) as s:
        s.execute(update(models.QuestionBank).where(models.QuestionBank.id == qid).values(status="retired"))


def test_question_external_id_version_unique(tenant_factory):
    t = tenant_factory()
    with pytest.raises(IntegrityError):
        with db.tenant_session(t.id) as s:
            t.new_question(s, external_id="DUP-1")
            t.new_question(s, external_id="DUP-1")


# -------------------------------------------------------------- intentos ---


def _session_with_question(s, t):
    q = t.new_question(s)
    t.add_options(s, q)
    sess = models.ExamAttempt(
        university_id=t.id,
        exam_id=t.exam_id,
        student_id=t.student_id,
        window_deadline_at=datetime.now(UTC) + timedelta(minutes=80),
        seed=secrets.token_hex(16),
        config_snapshot={"exam_size": 200},
        full_name_entered="Alumno Demo",
        token_hash=secrets.token_hex(32),
    )
    s.add(sess)
    s.flush()
    now = datetime.now(UTC)
    s.add(
        models.AttemptQuestion(
            university_id=t.id,
            attempt_id=sess.id,
            ordinal=1,
            question_id=q.id,
            module_number=1,
            options_order=["C", "A", "D", "B"],
            served_at=now,
            deadline_at=now + timedelta(seconds=20),
            state="served",
        )
    )
    s.flush()
    opt = s.scalars(
        select(models.QuestionOption).where(
            models.QuestionOption.question_id == q.id, models.QuestionOption.option_code == "B"
        )
    ).one()
    return sess, opt


def test_single_attempt_per_student_and_version(tenant_factory):
    t = tenant_factory()
    with pytest.raises(IntegrityError):
        with db.tenant_session(t.id) as s:
            _session_with_question(s, t)
            _session_with_question(s, t)  # mismo alumno, misma convocatoria, attempt_number=1


def test_answer_is_unique_per_ordinal_and_idempotency_key(tenant_factory):
    t = tenant_factory()
    with db.tenant_session(t.id) as s:
        sess, opt = _session_with_question(s, t)
        s.add(
            models.AttemptAnswer(
                university_id=t.id,
                attempt_id=sess.id,
                ordinal=1,
                selected_option_id=opt.id,
                outcome="correct",
                idempotency_key="k1",
            )
        )
        sid = sess.id
    with pytest.raises(IntegrityError):
        with db.tenant_session(t.id) as s:
            s.add(
                models.AttemptAnswer(
                    university_id=t.id, attempt_id=sid, ordinal=1, outcome="omitted", idempotency_key="k2"
                )
            )
            s.flush()


def test_answers_are_append_only(tenant_factory):
    t = tenant_factory()
    with db.tenant_session(t.id) as s:
        sess, _ = _session_with_question(s, t)
        s.add(
            models.AttemptAnswer(
                university_id=t.id, attempt_id=sess.id, ordinal=1, outcome="omitted", idempotency_key="k"
            )
        )
        sid = sess.id
    with pytest.raises(DBAPIError, match="append-only"):
        with db.tenant_session(t.id) as s:
            s.execute(
                update(models.AttemptAnswer).where(models.AttemptAnswer.attempt_id == sid).values(outcome="correct")
            )


def test_selected_option_must_match_outcome(tenant_factory):
    t = tenant_factory()
    with pytest.raises(IntegrityError):
        with db.tenant_session(t.id) as s:
            sess, _ = _session_with_question(s, t)
            s.add(
                models.AttemptAnswer(
                    university_id=t.id, attempt_id=sess.id, ordinal=1, outcome="correct", idempotency_key="k"
                )
            )
            s.flush()


@pytest.mark.parametrize(
    ("counts", "grade"),
    [((150, 25, 25, 0), 62.5), ((100, 50, 50, 0), 25.0)],
)
def test_results_accept_consistent_counts(tenant_factory, counts, grade):
    t = tenant_factory()
    c, w, o, e = counts
    with db.tenant_session(t.id) as s:
        sess, _ = _session_with_question(s, t)
        s.add(
            models.AttemptResult(
                university_id=t.id,
                attempt_id=sess.id,
                total=200,
                correct=c,
                wrong=w,
                omitted=o,
                expired=e,
                raw_score=c - w,
                grade=grade,
            )
        )


@pytest.mark.parametrize(("counts", "grade"), [((150, 25, 20, 0), 62.5), ((10, 190, 0, 0), -90)])
def test_results_reject_inconsistent_counts_or_negative_grade(tenant_factory, counts, grade):
    t = tenant_factory()
    c, w, o, e = counts
    with pytest.raises(IntegrityError):
        with db.tenant_session(t.id) as s:
            sess, _ = _session_with_question(s, t)
            s.add(
                models.AttemptResult(
                    university_id=t.id,
                    attempt_id=sess.id,
                    total=200,
                    correct=c,
                    wrong=w,
                    omitted=o,
                    expired=e,
                    raw_score=c - w,
                    grade=grade,
                )
            )
            s.flush()


def test_audit_events_are_append_only(tenant_factory):
    t = tenant_factory()
    with db.tenant_session(t.id) as s:
        ev = models.AuditEvent(university_id=t.id, actor_type="system", event_type="test")
        s.add(ev)
        s.flush()
        eid = ev.id
    with pytest.raises(DBAPIError, match="append-only"):
        with db.tenant_session(t.id) as s:
            s.execute(update(models.AuditEvent).where(models.AuditEvent.id == eid).values(event_type="x"))
