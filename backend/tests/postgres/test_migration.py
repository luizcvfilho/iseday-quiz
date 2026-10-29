from datetime import UTC, datetime, timedelta
from io import StringIO

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.db import Base
from app.models import AdminAuditLog, AdminSession, AdminUser, School

from .conftest import migration_config
from .helpers import catalog, feedback, participation, results, selections, submit

pytestmark = pytest.mark.postgres


def test_upgrade_downgrade_reupgrade_and_metadata(empty_database):
    with empty_database.begin() as db:
        config = migration_config(db)
        command.upgrade(config, "head")
        assert set(inspect(db).get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0001"
        context = MigrationContext.configure(db, opts={"compare_server_default": True})
        assert compare_metadata(context, Base.metadata) == []

        # Downgrade must also work with a completed participation and immutable catalog.
        quiz = catalog(db)
        participant = participation(db, quiz)
        selections(db, quiz, participant)
        results(db, quiz, participant)
        submit(db, participant)
        feedback(db, participant, course=quiz.courses[0])
        db.execute(
            text(
                "UPDATE participations SET status='completed', completed_at=now() "
                "+ interval '1 minute' WHERE id=:id"
            ),
            {"id": participant},
        )
        command.downgrade(config, "base")
        assert inspect(db).get_table_names() == ["alembic_version"]
        assert (
            db.scalar(
                text(
                    "SELECT count(*) FROM pg_proc p JOIN pg_namespace n "
                    "ON n.oid=p.pronamespace WHERE n.nspname=current_schema()"
                )
            )
            == 0
        )
        command.upgrade(config, "head")
        assert compare_metadata(MigrationContext.configure(db), Base.metadata) == []


def test_orm_defaults_sessions_and_audit_retention(db):
    with Session(db, join_transaction_mode="create_savepoint") as session:
        school = School(name="Test school")
        admin = AdminUser(name="Admin", email="admin@example.org", password_hash="test-hash")
        session.add_all([school, admin])
        session.flush()
        assert school.id and school.created_at and school.is_active
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


def test_offline_sql_is_executable_and_reversible(empty_database):
    with empty_database.connect() as db:
        # Rendering SQL uses a dummy URL and never reads the development configuration.
        base_config = migration_config(db)
        upgrade_sql = StringIO()
        config = Config(base_config.config_file_name, output_buffer=upgrade_sql)
        config.set_main_option("sqlalchemy.url", "postgresql+psycopg://test@localhost/iseday_test")
        command.upgrade(config, "head", sql=True)
        db.execution_options(isolation_level="AUTOCOMMIT", no_parameters=True).exec_driver_sql(
            upgrade_sql.getvalue()
        )
        assert set(inspect(db).get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}

        downgrade_sql = StringIO()
        config.output_buffer = downgrade_sql
        command.downgrade(config, "0001:base", sql=True)
        db.exec_driver_sql(downgrade_sql.getvalue())
        assert inspect(db).get_table_names() == ["alembic_version"]
