from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from time import monotonic, sleep

import pytest
from alembic import command
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError

from app.models import Participation, ParticipationSelection, QuizVersion, StatementCourseWeight

from .conftest import migration_config
from .helpers import catalog, participation, results, selections, submit

pytestmark = pytest.mark.postgres


def run_blocked_statement(engine, backend_pid, statement):
    with engine.begin() as db:
        db.execute(text("SET LOCAL statement_timeout = '5s'"))
        backend_pid.put(db.scalar(text("SELECT pg_backend_pid()")))
        db.execute(statement)


def assert_waits_for_lock(db, pid):
    deadline = monotonic() + 3
    while monotonic() < deadline:
        if db.scalar(text("SELECT cardinality(pg_blocking_pids(:pid)) > 0"), {"pid": pid}):
            return
        sleep(0.01)
    pytest.fail("Concurrent write did not wait for the parent row lock")


@pytest.fixture
def concurrent_database(empty_database):
    with empty_database.begin() as db:
        command.upgrade(migration_config(db), "head")
    return empty_database


def test_submission_waits_for_selection_write_and_rechecks_count(concurrent_database):
    engine = concurrent_database
    with engine.begin() as db:
        quiz = catalog(db)
        participant = participation(db, quiz)
        selections(db, quiz, participant)
        results(db, quiz, participant)

    backend_pid = Queue()
    with ThreadPoolExecutor(max_workers=1) as executor:
        with engine.connect() as writer:
            transaction = writer.begin()
            try:
                writer.execute(
                    delete(ParticipationSelection).where(
                        ParticipationSelection.statement_id == quiz.statements[0]
                    )
                )
                statement = (
                    update(Participation)
                    .where(Participation.id == participant)
                    .values(status="submitted", submitted_at=text("clock_timestamp()"))
                )
                future = executor.submit(run_blocked_statement, engine, backend_pid, statement)
                assert_waits_for_lock(writer, backend_pid.get(timeout=3))
            finally:
                transaction.commit()
        with pytest.raises(DBAPIError, match="exactly 25.*24"):
            future.result(timeout=6)
    with engine.connect() as db:
        assert db.scalar(select(Participation.status)) == "draft"


def test_publication_waits_for_catalog_write_and_revalidates(concurrent_database):
    engine = concurrent_database
    with engine.begin() as db:
        quiz = catalog(db, publish=False)
    backend_pid = Queue()
    with ThreadPoolExecutor(max_workers=1) as executor:
        with engine.connect() as writer:
            transaction = writer.begin()
            try:
                writer.execute(
                    delete(StatementCourseWeight).where(
                        StatementCourseWeight.statement_id == quiz.statements[-1]
                    )
                )
                future = executor.submit(
                    run_blocked_statement,
                    engine,
                    backend_pid,
                    update(QuizVersion).values(status="published"),
                )
                assert_waits_for_lock(writer, backend_pid.get(timeout=3))
            finally:
                transaction.commit()
        with pytest.raises(DBAPIError, match="Every statement"):
            future.result(timeout=6)
    with engine.connect() as db:
        assert db.scalar(select(QuizVersion.status)) == "draft"


def test_submission_blocks_late_changes_to_results_and_selections(concurrent_database):
    engine = concurrent_database
    with engine.begin() as db:
        quiz = catalog(db)
        participant = participation(db, quiz)
        selections(db, quiz, participant)
        results(db, quiz, participant)
    backend_pid = Queue()
    with ThreadPoolExecutor(max_workers=1) as executor:
        with engine.connect() as writer:
            transaction = writer.begin()
            try:
                submit(writer, participant)
                future = executor.submit(
                    run_blocked_statement, engine, backend_pid, delete(ParticipationSelection)
                )
                assert_waits_for_lock(writer, backend_pid.get(timeout=3))
            finally:
                transaction.commit()
        with pytest.raises(DBAPIError, match="Submitted answers and results are immutable"):
            future.result(timeout=6)
