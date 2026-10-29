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
    QuizVersion,
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
            quiz_version_id=quiz.version,
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
def test_participation_children_cannot_mix_versions(db, quiz, draft, model, key):
    other = catalog(db, number=2, publish=False)
    foreign_id = {
        "statement_id": other.statements[0],
        "area_id": other.areas[0],
        "course_id": other.courses[0],
    }[key]
    values = dict(participation_id=draft, quiz_version_id=quiz.version, **{key: foreign_id})
    if model is ParticipationAreaResult:
        values.update(score=1, is_winner=True)
    elif model is ParticipationCourseResult:
        values.update(score=1, is_recommended=True)
    rejects(db, insert(model).values(**values), "foreign key", IntegrityError)


@pytest.mark.parametrize("target", ["course_area", "weight_course", "weight_statement"])
def test_catalog_links_cannot_mix_versions(db, quiz, target):
    other = catalog(db, number=2, publish=False)
    if target == "course_area":
        stmt = insert(Course).values(
            quiz_version_id=other.version, area_id=quiz.areas[0], name="Bad"
        )
    else:
        stmt = insert(StatementCourseWeight).values(
            quiz_version_id=other.version,
            statement_id=quiz.statements[0]
            if target == "weight_statement"
            else other.statements[0],
            course_id=quiz.courses[0] if target == "weight_course" else other.courses[1],
        )
    rejects(db, stmt, "foreign key", IntegrityError)


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
        stmt = update(table).values(quiz_version_id=quiz.version)
    else:
        stmt = delete(table)
    rejects(db, stmt, "Submitted answers and results are immutable")


@pytest.mark.parametrize("model", [Area, Course, Statement, StatementCourseWeight])
@pytest.mark.parametrize("operation", ["insert", "update", "delete"])
def test_published_catalog_is_immutable(db, quiz, model, operation):
    table = model.__table__
    if operation == "insert":
        stmt = insert(table).from_select(list(table.c.keys()), select(table))
    elif operation == "update":
        stmt = update(table).values(quiz_version_id=quiz.version)
    else:
        stmt = delete(table)
    rejects(db, stmt, "immutable")


@pytest.mark.parametrize(
    "defect,message",
    [
        ("count", "at least 25"),
        ("unmapped_statement", "Every statement"),
        ("unmapped_course", "Every course"),
        ("empty_area", "Every area"),
    ],
)
def test_publication_validates_catalog(db, defect, message):
    quiz = catalog(db, publish=False, count=24 if defect == "count" else 26)
    if defect == "unmapped_statement":
        db.execute(
            delete(StatementCourseWeight).where(
                StatementCourseWeight.statement_id == quiz.statements[-1]
            )
        )
    elif defect == "unmapped_course":
        db.execute(
            delete(StatementCourseWeight).where(StatementCourseWeight.course_id == quiz.courses[1])
        )
    elif defect == "empty_area":
        db.execute(
            insert(Area).values(
                quiz_version_id=quiz.version,
                name="Empty area",
                destination="Space",
                destination_instructions="Directions",
            )
        )
    rejects(db, update(QuizVersion).values(status="published"), message)


def test_only_one_published_version_and_archival_keeps_history(db, quiz, draft):
    other = catalog(db, number=2, publish=False)
    rejects(
        db,
        update(QuizVersion).where(QuizVersion.id == other.version).values(status="published"),
        "duplicate key",
        IntegrityError,
    )
    db.execute(update(QuizVersion).where(QuizVersion.id == quiz.version).values(status="archived"))
    db.execute(
        update(QuizVersion).where(QuizVersion.id == other.version).values(status="published")
    )
    selections(db, quiz, draft)
    results(db, quiz, draft)
    submit(db, draft)  # A session already in progress may finish its archived version.
    with pytest.raises(DBAPIError, match="published version"), db.begin_nested():
        participation(db, quiz)
    rejects(
        db,
        update(QuizVersion).where(QuizVersion.id == quiz.version).values(status="draft"),
        "immutable",
    )
    rejects(db, delete(QuizVersion).where(QuizVersion.id == quiz.version), "cannot be deleted")


def test_feedback_requires_submitted_participation(db, draft):
    with pytest.raises(DBAPIError, match="requires a submitted"), db.begin_nested():
        feedback(db, draft, agrees=False)


def test_feedback_requires_recommended_course(db, quiz, submitted):
    with pytest.raises(DBAPIError, match="recommended courses"), db.begin_nested():
        feedback(db, submitted, course=quiz.courses[1])


@pytest.mark.parametrize("agrees,chosen", [(True, None), (False, 0)])
def test_feedback_choice_matches_agreement(db, quiz, submitted, agrees, chosen):
    with pytest.raises(DBAPIError), db.begin_nested():
        feedback(
            db, submitted, agrees=agrees, course=None if chosen is None else quiz.courses[chosen]
        )


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
    assert db.scalar(select(func.count()).select_from(QuizVersion)) == 1


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
        update(Participation).values(quiz_version_id=func.gen_random_uuid()),
        "identity/version cannot change",
    )


def test_cannot_start_participation_on_draft_catalog(db):
    quiz = catalog(db, publish=False)
    with pytest.raises(DBAPIError, match="published version"), db.begin_nested():
        participation(db, quiz)


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
