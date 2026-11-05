from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import insert, update

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


@dataclass
class Catalog:
    version: UUID
    areas: list[UUID]
    courses: list[UUID]
    statements: list[UUID]


def catalog(db, *, number=1, count=26, publish=True):
    """Synthetic mappings: two tied areas, two recommendations and one lower course."""
    quiz = Catalog(
        uuid4(), [uuid4(), uuid4()], [uuid4() for _ in range(3)], [uuid4() for _ in range(count)]
    )
    db.execute(
        insert(QuizVersion).values(
            id=quiz.version,
            event_name="Test event",
            version_number=number,
            psychology_destination="SPA",
            psychology_instructions="Find the Psychology team",
        )
    )
    db.execute(
        insert(Area),
        [
            dict(
                id=area,
                quiz_version_id=quiz.version,
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
                quiz_version_id=quiz.version,
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
                    quiz_version_id=quiz.version,
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
                    quiz_version_id=quiz.version,
                    statement_id=statement,
                    course_id=course,
                )
                for statement in quiz.statements
                for course in (quiz.courses[0], quiz.courses[2])
            ],
        )
        db.execute(
            insert(StatementCourseWeight).values(
                quiz_version_id=quiz.version,
                statement_id=quiz.statements[0],
                course_id=quiz.courses[1],
            )
        )
    if publish:
        db.execute(
            update(QuizVersion).where(QuizVersion.id == quiz.version).values(status="published")
        )
    return quiz


def participation(db, quiz):
    return db.scalar(
        insert(Participation)
        .values(
            quiz_version_id=quiz.version,
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
                quiz_version_id=quiz.version,
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
                quiz_version_id=quiz.version,
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
                quiz_version_id=quiz.version,
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
