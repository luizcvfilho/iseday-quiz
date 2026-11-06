from uuid import uuid4

import pytest
from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.models import (
    Area,
    Course,
    Participation,
    ParticipationAreaResult,
    ParticipationCourseResult,
    ParticipationFeedback,
    ParticipationSelection,
    Statement,
    StatementCourseWeight,
)

from .helpers import catalog, feedback, participation, results, selections, submit

pytestmark = pytest.mark.postgres


@pytest.fixture
def quiz(db):
    return catalog(db)


@pytest.fixture
def draft(db, quiz):
    return participation(db, quiz)


@pytest.fixture
def submitted(db, quiz, draft):
    selections(db, quiz, draft)
    results(db, quiz, draft)
    submit(db, draft)
    return draft


def rejects(db, statement, message, error=DBAPIError):
    with pytest.raises(error, match=message), db.begin_nested():
        db.execute(statement)


@pytest.mark.parametrize("count", [24, 26])
def test_submission_requires_exactly_25_and_rolls_back_partial_writes(db, quiz, draft, count):
    with pytest.raises(DBAPIError, match="exactly 25"), db.begin_nested():
        selections(db, quiz, draft, count=count)
        results(db, quiz, draft)
        submit(db, draft)
    for model in (ParticipationSelection, ParticipationAreaResult, ParticipationCourseResult):
        assert db.scalar(select(func.count()).select_from(model)) == 0
    assert db.scalar(select(Participation.status)) == "draft"


def test_duplicate_selection_rejected(db, quiz, draft):
    selections(db, quiz, draft)
    rejects(
        db,
        insert(ParticipationSelection).values(
            participation_id=draft,
            statement_id=quiz.statements[0],
        ),
        "duplicate key",
        IntegrityError,
    )


@pytest.mark.parametrize(
    "model,key",
    [
        (ParticipationSelection, "statement_id"),
        (ParticipationAreaResult, "area_id"),
        (ParticipationCourseResult, "course_id"),
    ],
)
def test_participation_children_require_known_catalog_items(db, quiz, draft, model, key):
    values = dict(participation_id=draft, **{key: uuid4()})
    if model is ParticipationAreaResult:
        values.update(score=1, is_winner=True)
    elif model is ParticipationCourseResult:
        values.update(score=1, is_recommended=True)
    rejects(db, insert(model).values(**values), "foreign key", IntegrityError)


@pytest.mark.parametrize("model", [ParticipationAreaResult, ParticipationCourseResult])
def test_submission_requires_all_results(db, quiz, draft, model):
    selections(db, quiz, draft)
    results(db, quiz, draft)
    db.execute(delete(model))
    with pytest.raises(DBAPIError, match="every area and course"), db.begin_nested():
        submit(db, draft)


@pytest.mark.parametrize(
    "model,flag",
    [
        (ParticipationAreaResult, "is_winner"),
        (ParticipationCourseResult, "is_recommended"),
    ],
)
def test_submission_requires_winners_and_recommendations(db, quiz, draft, model, flag):
    selections(db, quiz, draft)
    results(db, quiz, draft)
    db.execute(update(model).values(**{flag: False}))
    with pytest.raises(DBAPIError, match="winning area and recommended course"), db.begin_nested():
        submit(db, draft)


def test_valid_submission_preserves_multiple_winners(db, quiz, submitted):
    assert db.scalar(select(Participation.status)) == "submitted"
    assert (
        db.scalar(
            select(func.count())
            .select_from(ParticipationAreaResult)
            .where(ParticipationAreaResult.is_winner)
        )
        == 2
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(ParticipationCourseResult)
            .where(ParticipationCourseResult.is_recommended)
        )
        == 2
    )


@pytest.mark.parametrize(
    "model",
    [
        ParticipationSelection,
        ParticipationAreaResult,
        ParticipationCourseResult,
    ],
)
@pytest.mark.parametrize("operation", ["insert", "update", "delete"])
def test_submitted_answers_and_results_are_immutable(db, quiz, submitted, model, operation):
    table = model.__table__
    if operation == "insert":
        stmt = insert(table).from_select(list(table.c.keys()), select(table))
    elif operation == "update":
        stmt = update(table).values(**{list(table.c.keys())[0]: table.c[list(table.c.keys())[0]]})
    else:
        stmt = delete(table)
    rejects(db, stmt, "Submitted answers and results are immutable")


@pytest.mark.parametrize("model", [Area, Course, Statement, StatementCourseWeight])
@pytest.mark.parametrize("operation", ["insert", "update", "delete"])
def test_fixed_catalog_is_immutable(db, quiz, model, operation):
    table = model.__table__
    if operation == "insert":
        stmt = insert(table).from_select(list(table.c.keys()), select(table))
    elif operation == "update":
        stmt = update(table).values(**{list(table.c.keys())[0]: table.c[list(table.c.keys())[0]]})
    else:
        stmt = delete(table)
    rejects(db, stmt, "fixed and cannot be changed")


def test_feedback_requires_submitted_participation(db, draft):
    with pytest.raises(DBAPIError, match="requires a submitted"), db.begin_nested():
        feedback(db, draft, agrees=False)


def test_feedback_requires_recommended_course(db, quiz, submitted):
    with pytest.raises(DBAPIError, match="recommended courses"), db.begin_nested():
        feedback(db, submitted, course=quiz.courses[1])


def test_feedback_disagreement_rejects_a_course(db, quiz, submitted):
    with pytest.raises(DBAPIError), db.begin_nested():
        feedback(db, submitted, agrees=False, course=quiz.courses[0])


def test_feedback_allows_agreement_without_a_course(db, submitted):
    feedback(db, submitted, agrees=True)
    db.execute(
        update(Participation).values(status="completed", completed_at=func.clock_timestamp())
    )
    assert db.scalar(select(ParticipationFeedback.agrees_with_result)) is True
    assert db.scalar(select(ParticipationFeedback.chosen_course_id)) is None


def test_completion_requires_feedback(db, submitted):
    rejects(
        db,
        update(Participation).values(status="completed", completed_at=func.clock_timestamp()),
        "requires feedback",
    )


@pytest.mark.parametrize("agrees", [True, False])
def test_feedback_completion_immutability_and_controlled_retention(db, quiz, submitted, agrees):
    feedback(db, submitted, course=quiz.courses[0] if agrees else None, agrees=agrees)
    db.execute(
        update(Participation).values(
            status="completed", completed_at=func.clock_timestamp(), access_token_hash=None
        )
    )
    rejects(
        db, update(ParticipationFeedback).values(destination="Changed"), "Feedback is immutable"
    )
    rejects(db, delete(ParticipationFeedback), "Feedback is immutable")
    rejects(
        db,
        update(Participation).values(completed_at=func.clock_timestamp()),
        "details are immutable",
    )
    db.execute(delete(Participation).where(Participation.id == submitted))
    for model in (
        Participation,
        ParticipationSelection,
        ParticipationAreaResult,
        ParticipationCourseResult,
        ParticipationFeedback,
    ):
        assert db.scalar(select(func.count()).select_from(model)) == 0
    assert db.scalar(select(func.count()).select_from(Statement)) == 26


@pytest.mark.parametrize(
    "values",
    [
        {"full_name": "Changed"},
        {"email": "changed@example.org"},
        {"phone": "+5511988888888"},
        {"privacy_notice_version": "other"},
        {"submitted_at": func.clock_timestamp()},
    ],
)
def test_submitted_registration_is_immutable(db, submitted, values):
    rejects(db, update(Participation).values(**values), "details are immutable")
    db.execute(update(Participation).values(access_token_hash=None))


def test_no_backward_or_skipped_state_transition(db, draft):
    rejects(
        db,
        update(Participation).values(status="completed", completed_at=func.clock_timestamp()),
        "Invalid participation state transition",
    )
    rejects(
        db,
        update(Participation).values(id=func.gen_random_uuid()),
        "identity cannot change",
    )


def test_admin_email_uniqueness_is_case_insensitive(db):
    db.execute(
        text(
            "INSERT INTO admin_users (name,email,password_hash) "
            "VALUES ('Admin','Admin@example.org','hash')"
        )
    )
    rejects(
        db,
        text(
            "INSERT INTO admin_users (name,email,password_hash) "
            "VALUES ('Other','admin@example.org','hash')"
        ),
        "duplicate key",
        IntegrityError,
    )


@pytest.mark.parametrize("table", ["areas", "courses", "statements", "statement_course_weights"])
def test_fixed_catalog_cannot_be_truncated(db, table):
    rejects(db, text(f"TRUNCATE {table} CASCADE"), "fixed and cannot be changed")
