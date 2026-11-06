from datetime import UTC, datetime, timedelta
from io import StringIO

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import event, inspect, select, text
from sqlalchemy.orm import Session

from app.db import Base
from app.models import AdminAuditLog, AdminSession, AdminUser

from .conftest import migration_config

pytestmark = pytest.mark.postgres


def seed_legacy_database(connection):
    command.upgrade(migration_config(connection), "0002")
    version = connection.scalar(
        text("""
        INSERT INTO quiz_versions (event_name, version_number, psychology_destination,
            psychology_instructions) VALUES ('Old event', 1, 'SPA', 'Old instructions') RETURNING id
    """)
    )
    connection.execute(
        text("""
        INSERT INTO quiz_versions (event_name, version_number, psychology_destination,
            psychology_instructions) VALUES ('Unused draft', 2, 'SPA', 'Instructions')
    """)
    )
    area = connection.scalar(
        text("""
        INSERT INTO areas (quiz_version_id, name, destination, destination_instructions)
        VALUES (:version, 'Old area', 'Old destination', 'Old instructions') RETURNING id
    """),
        {"version": version},
    )
    course = connection.scalar(
        text("""
        INSERT INTO courses (quiz_version_id, area_id, name)
        VALUES (:version, :area, 'Enfermagem') RETURNING id
    """),
        {"version": version, "area": area},
    )
    connection.execute(
        text("""
        INSERT INTO statements (quiz_version_id, source_number, display_order, text)
        SELECT :version, n, n, 'Old statement ' || n FROM generate_series(1, 25) n
    """),
        {"version": version},
    )
    connection.execute(
        text("""
        INSERT INTO statement_course_weights (quiz_version_id, statement_id, course_id)
        SELECT :version, id, :course FROM statements
    """),
        {"version": version, "course": course},
    )
    connection.execute(
        text("UPDATE quiz_versions SET status='published' WHERE id=:id"), {"id": version}
    )
    participant = connection.scalar(
        text("""
        INSERT INTO participations (quiz_version_id, school_name, full_name, phone, email,
            privacy_notice_version, access_expires_at, access_token_hash)
        VALUES (:version, 'Test school', 'Test name', '+5511999999999', 'test@example.org',
            'test', now() + interval '1 hour', repeat('a', 64)) RETURNING id
    """),
        {"version": version},
    )
    connection.execute(
        text("""
        INSERT INTO participation_selections (participation_id, quiz_version_id, statement_id)
        SELECT :participant, :version, id FROM statements
    """),
        {"participant": participant, "version": version},
    )
    connection.execute(
        text("""
        INSERT INTO participation_area_results
            (participation_id, quiz_version_id, area_id, score, is_winner)
        VALUES (:participant, :version, :area, 25, true)
    """),
        {"participant": participant, "version": version, "area": area},
    )
    connection.execute(
        text("""
        INSERT INTO participation_course_results
            (participation_id, quiz_version_id, course_id, score, is_recommended)
        VALUES (:participant, :version, :course, 25, true)
    """),
        {"participant": participant, "version": version, "course": course},
    )
    connection.execute(
        text("UPDATE participations SET status='submitted', submitted_at=now() WHERE id=:id"),
        {"id": participant},
    )
    connection.execute(
        text("""
        INSERT INTO participation_feedback
            (participation_id, agrees_with_result, destination, destination_instructions)
        VALUES (:id, false, 'SPA', 'Instructions')
    """),
        {"id": participant},
    )
    connection.execute(
        text("UPDATE participations SET status='completed', completed_at=now() WHERE id=:id"),
        {"id": participant},
    )
    admin = connection.scalar(
        text("""
        INSERT INTO admin_users (name, email, password_hash)
        VALUES ('Admin', 'admin@example.org', 'preserved-hash') RETURNING id
    """)
    )
    connection.execute(
        text("""
        INSERT INTO admin_sessions (admin_user_id, token_hash, expires_at)
        VALUES (:id, repeat('b', 64), now() + interval '1 hour')
    """),
        {"id": admin},
    )
    connection.execute(
        text("""
        INSERT INTO admin_audit_logs (admin_user_id, action, target_participation_id)
        VALUES (:admin, 'participations.view', :participant)
    """),
        {"admin": admin, "participant": participant},
    )
    return admin


def test_upgrade_resets_test_data_preserves_admins_and_matches_metadata(empty_database):
    with empty_database.begin() as connection:
        admin_id = seed_legacy_database(connection)
        command.upgrade(migration_config(connection), "head")
        assert set(inspect(connection).get_table_names()) == set(Base.metadata.tables) | {
            "alembic_version"
        }
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0003"
        assert (
            compare_metadata(
                MigrationContext.configure(connection, opts={"compare_server_default": True}),
                Base.metadata,
            )
            == []
        )
        for table in (
            "participations",
            "participation_selections",
            "participation_area_results",
            "participation_course_results",
            "participation_feedback",
        ):
            assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 0
        assert connection.scalar(text("SELECT id FROM admin_users")) == admin_id
        assert connection.scalar(text("SELECT password_hash FROM admin_users")) == "preserved-hash"
        assert connection.scalar(text("SELECT count(*) FROM admin_sessions")) == 1
        assert connection.scalar(text("SELECT count(*) FROM admin_audit_logs")) == 1
        for table in Base.metadata.tables:
            assert "quiz_version_id" not in {
                c["name"] for c in inspect(connection).get_columns(table)
            }
        with pytest.raises(RuntimeError, match="restaure um backup"):
            command.downgrade(migration_config(connection), "0002")


def test_failed_migration_rolls_back_catalog_and_participation_deletion(empty_database):
    with empty_database.begin() as connection:
        seed_legacy_database(connection)

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
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0002"
        assert connection.scalar(text("SELECT count(*) FROM quiz_versions")) == 2
        assert connection.scalar(text("SELECT count(*) FROM participations")) == 1
        assert connection.scalar(text("SELECT count(*) FROM participation_feedback")) == 1


def test_offline_sql_installs_the_fixed_catalog(empty_database):
    with empty_database.connect() as connection:
        output = StringIO()
        config = Config(migration_config(connection).config_file_name, output_buffer=output)
        config.set_main_option("sqlalchemy.url", "postgresql+psycopg://test@localhost/iseday_test")
        command.upgrade(config, "head", sql=True)
        connection.execution_options(
            isolation_level="AUTOCOMMIT", no_parameters=True
        ).exec_driver_sql(output.getvalue())
        assert set(inspect(connection).get_table_names()) == set(Base.metadata.tables) | {
            "alembic_version"
        }
        assert connection.scalar(text("SELECT count(*) FROM courses")) == 9


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
