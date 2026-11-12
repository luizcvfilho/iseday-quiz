from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import bindparam, delete, insert, text, update

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


CATALOG_TABLES = ("areas", "courses", "statements", "statement_course_weights")


def catalog(engine, *, course_destination=None, single_recommendation=False):
    """Install a synthetic catalog in a disposable test schema before transactions begin."""
    with engine.begin() as db:
        triggers = db.scalars(
            text(
                "SELECT TRIGGER_NAME FROM information_schema.TRIGGERS "
                "WHERE TRIGGER_SCHEMA = DATABASE() AND EVENT_OBJECT_TABLE IN :tables"
            ).bindparams(bindparam("tables", expanding=True)),
            {"tables": CATALOG_TABLES},
        ).all()
        definitions = []
        for trigger in triggers:
            definitions.append(
                db.exec_driver_sql(f"SHOW CREATE TRIGGER `{trigger}`")
                .mappings()
                .one()["SQL Original Statement"]
            )
            db.exec_driver_sql(f"DROP TRIGGER `{trigger}`")
        quiz = seed_catalog(db, course_destination, single_recommendation)
        for statement in definitions:
            # MySQL may return a definer such as root@%, with a literal percent sign.
            db.exec_driver_sql(statement, execution_options={"no_parameters": True})
    return quiz


def seed_catalog(db, course_destination, single_recommendation):
    """Synthetic mappings: two tied areas, two recommendations and one lower course."""
    for model in (StatementCourseWeight, Statement, Course, Area):
        db.execute(delete(model))
    quiz = Catalog([uuid4(), uuid4()], [uuid4() for _ in range(3)], [uuid4() for _ in range(26)])
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
    destination, instructions = course_destination or (None, None)
    db.execute(
        insert(Course),
        [
            dict(
                id=course,
                area_id=quiz.areas[0 if i < 2 else 1],
                name=f"Course {i}",
                destination=destination if i == 0 else None,
                destination_instructions=instructions if i == 0 else None,
            )
            for i, course in enumerate(quiz.courses)
        ],
    )
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
            for course in (quiz.courses[:1] if single_recommendation else quiz.courses[::2])
        ],
    )
    db.execute(
        insert(StatementCourseWeight).values(
            statement_id=quiz.statements[0],
            course_id=quiz.courses[1],
        )
    )
    return quiz


def participation(db):
    participant = uuid4()
    db.execute(
        insert(Participation).values(
            id=participant,
            school_name="Test school",
            full_name="Test participant",
            phone="+5511999999999",
            email="participant@example.org",
            privacy_notice_version="test-v1",
            access_expires_at=datetime.now(UTC) + timedelta(hours=1),
            access_token_hash=uuid4().hex + uuid4().hex,
        )
    )
    return participant


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
