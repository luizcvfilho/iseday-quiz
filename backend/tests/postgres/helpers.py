from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, insert, text, update

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


@dataclass
class Catalog:
    areas: list[UUID]
    courses: list[UUID]
    statements: list[UUID]


def catalog(db, *, count=26):
    """Synthetic mappings: two tied areas, two recommendations and one lower course."""
    # Synthetic content exists only in the disposable test schema.
    for table in ("areas", "courses", "statements", "statement_course_weights"):
        db.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER USER"))
    for model in (StatementCourseWeight, Statement, Course, Area):
        db.execute(delete(model))
    quiz = Catalog([uuid4(), uuid4()], [uuid4() for _ in range(3)], [uuid4() for _ in range(count)])
    db.execute(
        insert(Area),
        [
            dict(
                id=area,
                name=f"Area {i}",
                destination="Space",
                destination_instructions="Go to the indicated space",
            )
            for i, area in enumerate(quiz.areas)
        ],
    )
    db.execute(
        insert(Course),
        [
            dict(
                id=course,
                area_id=quiz.areas[0 if i < 2 else 1],
                name=f"Course {i}",
            )
            for i, course in enumerate(quiz.courses)
        ],
    )
    if count:
        db.execute(
            insert(Statement),
            [
                dict(
                    id=statement,
                    source_number=i,
                    display_order=i,
                    text=f"Statement {i}",
                )
                for i, statement in enumerate(quiz.statements, start=1)
            ],
        )
        db.execute(
            insert(StatementCourseWeight),
            [
                dict(
                    statement_id=statement,
                    course_id=course,
                )
                for statement in quiz.statements
                for course in (quiz.courses[0], quiz.courses[2])
            ],
        )
        db.execute(
            insert(StatementCourseWeight).values(
                statement_id=quiz.statements[0],
                course_id=quiz.courses[1],
            )
        )
    for table in ("areas", "courses", "statements", "statement_course_weights"):
        db.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER USER"))
    return quiz


def participation(db, quiz):
    return db.scalar(
        insert(Participation)
        .values(
            school_name="Test school",
            full_name="Test participant",
            phone="+5511999999999",
            email="participant@example.org",
            privacy_notice_version="test-v1",
            access_expires_at=datetime.now(UTC) + timedelta(hours=1),
            access_token_hash=uuid4().hex + uuid4().hex,
        )
        .returning(Participation.id)
    )


def selections(db, quiz, participant, *, count=25):
    db.execute(
        insert(ParticipationSelection),
        [
            dict(
                participation_id=participant,
                statement_id=statement,
            )
            for statement in quiz.statements[:count]
        ],
    )


def results(db, quiz, participant):
    db.execute(
        insert(ParticipationAreaResult),
        [
            dict(
                participation_id=participant,
                area_id=area,
                score=25,
                is_winner=True,
            )
            for area in quiz.areas
        ],
    )
    db.execute(
        insert(ParticipationCourseResult),
        [
            dict(
                participation_id=participant,
                course_id=course,
                score=1 if i == 1 else 25,
                is_recommended=i != 1,
            )
            for i, course in enumerate(quiz.courses)
        ],
    )


def submit(db, participant):
    db.execute(
        update(Participation)
        .where(Participation.id == participant)
        .values(
            status="submitted",
            submitted_at=datetime.now(UTC),
        )
    )


def feedback(db, participant, *, course=None, agrees=True):
    db.execute(
        insert(ParticipationFeedback).values(
            participation_id=participant,
            agrees_with_result=agrees,
            chosen_course_id=course,
            destination="Space" if agrees else "SPA",
            destination_instructions="Find the team",
        )
    )
