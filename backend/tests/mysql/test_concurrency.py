from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from time import monotonic, sleep

import pytest
from alembic import command
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import DBAPIError

from app.db import database_now
from app.models import Participation, ParticipationSelection

from .conftest import migration_config
from .helpers import catalog, participation, results, selections, submit

pytestmark = pytest.mark.mysql


def run_blocked_statement(engine, connection_id, statement):
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as db:
        db.execute(text("SET SESSION innodb_lock_wait_timeout = 5"))
        # Pin the snapshot before the other writer commits, to verify current reads in the trigger.
        db.scalar(select(func.count()).select_from(ParticipationSelection))
        connection_id.put(db.scalar(text("SELECT CONNECTION_ID()")))
        db.execute(statement.prefix_with("/* concurrent test */"))
        db.commit()


def assert_waits_for_lock(db, connection_id, future):
    deadline = monotonic() + 3
    while monotonic() < deadline:
        statement = db.scalar(
            text("SELECT INFO FROM information_schema.PROCESSLIST WHERE ID = :connection_id"),
            {"connection_id": connection_id},
        )
        if statement and "concurrent test" in statement and not future.done():
            return
        if future.done():
            break
        sleep(0.01)
    pytest.fail("Concurrent write did not wait for the parent row lock")


@pytest.fixture
def concurrent_database(empty_database):
    with empty_database.begin() as db:
        command.upgrade(migration_config(db), "head")
    return empty_database, catalog(empty_database)


def test_submission_waits_for_selection_write_and_rechecks_count(concurrent_database):
    engine, quiz = concurrent_database
    with engine.begin() as db:
        participant = participation(db)
        selections(db, quiz, participant)
        results(db, quiz, participant)

    connection_id = Queue()
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
                    .values(status="submitted", submitted_at=database_now())
                )
                future = executor.submit(run_blocked_statement, engine, connection_id, statement)
                assert_waits_for_lock(writer, connection_id.get(timeout=3), future)
            finally:
                transaction.commit()
        with pytest.raises(DBAPIError, match="exactly 25.*24"):
            future.result(timeout=6)
    with engine.connect() as db:
        assert db.scalar(select(Participation.status)) == "draft"


def test_submission_blocks_late_changes_to_results_and_selections(concurrent_database):
    engine, quiz = concurrent_database
    with engine.begin() as db:
        participant = participation(db)
        selections(db, quiz, participant)
        results(db, quiz, participant)
    connection_id = Queue()
    with ThreadPoolExecutor(max_workers=1) as executor:
        with engine.connect() as writer:
            transaction = writer.begin()
            try:
                submit(writer, participant)
                future = executor.submit(
                    run_blocked_statement, engine, connection_id, delete(ParticipationSelection)
                )
                assert_waits_for_lock(writer, connection_id.get(timeout=3), future)
            finally:
                transaction.commit()
        with pytest.raises(DBAPIError, match="Submitted answers and results are immutable"):
            future.result(timeout=6)
