from datetime import UTC, datetime, timedelta
from io import StringIO

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import event, inspect, select, text, update
from sqlalchemy.orm import Session

from app.db import Base
from app.models import AdminAuditLog, AdminSession, AdminUser, Participation

from .conftest import migration_config
from .helpers import catalog, feedback, participation, results, selections, submit

pytestmark = pytest.mark.mysql


def assert_schema_matches_metadata(connection):
    assert set(inspect(connection).get_table_names()) == set(Base.metadata.tables) | {
        "alembic_version"
    }
    assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0001_mysql"
    assert (
        compare_metadata(
            MigrationContext.configure(connection, opts={"compare_server_default": True}),
            Base.metadata,
        )
        == []
    )


def schema_triggers(connection):
    return set(
        connection.scalars(
            text(
                "SELECT TRIGGER_NAME FROM information_schema.TRIGGERS "
                "WHERE TRIGGER_SCHEMA = DATABASE()"
            )
        )
    )


def test_initial_upgrade_creates_current_schema(empty_database):
    with empty_database.begin() as connection:
        command.upgrade(migration_config(connection), "head")
    with empty_database.connect() as connection:
        assert_schema_matches_metadata(connection)
        assert len(schema_triggers(connection)) == 26
        for table in (
            "participations",
            "participation_selections",
            "participation_area_results",
            "participation_course_results",
            "participation_feedback",
            "admin_users",
            "admin_sessions",
            "admin_audit_logs",
        ):
            assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 0


def test_downgrade_removes_schema_and_allows_fresh_upgrade(empty_database):
    with empty_database.begin() as connection:
        config = migration_config(connection)
        command.upgrade(config, "head")
    with empty_database.begin() as connection:
        config = migration_config(connection)
        command.downgrade(config, "base")
        assert inspect(connection).get_table_names() == ["alembic_version"]
        assert connection.scalar(text("SELECT count(*) FROM alembic_version")) == 0
        assert schema_triggers(connection) == set()
        command.upgrade(config, "head")
        assert_schema_matches_metadata(connection)
        assert connection.scalar(text("SELECT count(*) FROM statements")) == 74


def test_failed_seed_leaves_schema_unstamped_and_catalog_empty(empty_database):
    def fail_seed(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO courses"):
            raise RuntimeError("Simulated catalog failure")

    event.listen(empty_database, "before_cursor_execute", fail_seed)
    try:
        with pytest.raises(RuntimeError, match="Simulated catalog failure"):
            with empty_database.begin() as connection:
                command.upgrade(migration_config(connection), "head")
    finally:
        event.remove(empty_database, "before_cursor_execute", fail_seed)
    with empty_database.connect() as connection:
        # MySQL commits DDL separately, but the entire seed must roll back.
        assert set(inspect(connection).get_table_names()) == set(Base.metadata.tables) | {
            "alembic_version"
        }
        assert connection.scalar(text("SELECT count(*) FROM alembic_version")) == 0
        assert connection.scalar(text("SELECT count(*) FROM areas")) == 0
        assert schema_triggers(connection) == set()


def test_offline_sql_installs_the_fixed_catalog(empty_database):
    with empty_database.begin() as connection:
        output = StringIO()
        config = Config(migration_config(connection).config_file_name, output_buffer=output)
        config.set_main_option("sqlalchemy.url", "mysql+pymysql://test@localhost/iseday_test")
        command.upgrade(config, "head", sql=True)
        delimiter = ";"
        statement = ""
        for line in output.getvalue().splitlines(keepends=True):
            if not statement.strip() and line.startswith("DELIMITER "):
                delimiter = line.split()[1]
                continue
            statement += line
            if statement.rstrip().endswith(delimiter):
                connection.exec_driver_sql(statement.rstrip().removesuffix(delimiter))
                statement = ""
        assert not statement.strip()
        assert_schema_matches_metadata(connection)
        assert connection.scalar(text("SELECT count(*) FROM courses")) == 9
        assert len(schema_triggers(connection)) == 26


def test_orm_defaults_sessions_and_audit_retention(db):
    with Session(db, join_transaction_mode="create_savepoint") as session:
        admin = AdminUser(name="Admin", email="admin@example.org", password_hash="test-hash")
        session.add(admin)
        session.flush()
        session.add(
            AdminSession(
                admin_user_id=admin.id,
                token_hash="f" * 64,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        session.add(AdminAuditLog(admin_user_id=admin.id, action="view"))
        session.flush()
        session.delete(admin)
        session.flush()
        session.expire_all()
        assert session.scalar(select(AdminSession)) is None
        audit = session.scalar(select(AdminAuditLog))
        assert audit.id > 0 and audit.admin_user_id is None


def test_repeated_upgrade_preserves_feedback_and_accepts_automatic_referral(empty_database):
    with empty_database.begin() as connection:
        command.upgrade(migration_config(connection), "head")
    quiz = catalog(empty_database)
    with empty_database.begin() as connection:
        completed = participation(connection)
        pending = participation(connection)
        for participant in (completed, pending):
            selections(connection, quiz, participant)
            results(connection, quiz, participant)
            submit(connection, participant)
        feedback(connection, completed, course=quiz.courses[0])
        connection.execute(
            update(Participation)
            .where(Participation.id == completed)
            .values(status="completed", completed_at=datetime.now(UTC))
        )
        before = connection.execute(
            text("SELECT * FROM participation_feedback WHERE participation_id = :id"),
            {"id": completed.hex},
        ).one()
        command.upgrade(migration_config(connection), "head")
        after = connection.execute(
            text("SELECT * FROM participation_feedback WHERE participation_id = :id"),
            {"id": completed.hex},
        ).one()
        assert after == before
        feedback(connection, pending, agrees=True)
        connection.execute(
            update(Participation)
            .where(Participation.id == pending)
            .values(status="completed", completed_at=datetime.now(UTC))
        )
        assert (
            connection.scalar(
                text("SELECT status FROM participations WHERE id = :id"), {"id": pending.hex}
            )
            == "completed"
        )
