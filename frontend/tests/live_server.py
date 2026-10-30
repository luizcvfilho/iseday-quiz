"""Browser-test API with a disposable schema in an explicitly named *_test database."""

import os
from pathlib import Path
from uuid import uuid4

import uvicorn
from alembic import command
from alembic.config import Config
from app.admin.__main__ import save_account
from app.catalog import DEFAULT_WORKBOOK, import_catalog, read_catalog
from app.core.config import Settings
from app.db import get_session
from app.main import create_app
from app.models import QuizVersion, School
from sqlalchemy import create_engine, insert, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


def main():
    value = os.environ.get("TEST_DATABASE_URL", "")
    if not value:
        raise SystemExit("TEST_DATABASE_URL is required for browser integration checks")
    url = make_url(value)
    if url.drivername != "postgresql+psycopg" or not (url.database or "").endswith(
        "_test"
    ):
        raise SystemExit("Use postgresql+psycopg and a database ending in _test")
    schema = f"iseday_ui_{uuid4().hex}"
    admin = create_engine(url, hide_parameters=True)
    engine = create_engine(
        url, hide_parameters=True, connect_args={"options": f"-csearch_path={schema}"}
    )
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        with engine.begin() as connection:
            config = Config(
                str(Path(__file__).resolve().parents[2] / "backend" / "alembic.ini")
            )
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        imported = import_catalog(
            engine, read_catalog(DEFAULT_WORKBOOK), version_number=1
        )
        with engine.begin() as connection:
            connection.execute(
                update(QuizVersion)
                .where(QuizVersion.id == imported.version_id)
                .values(status="published")
            )
            connection.execute(insert(School).values(name="Escola de teste (fictícia)"))
        with Session(engine) as session, session.begin():
            save_account(
                session,
                "create",
                "admin@example.org",
                "admin test password only",
                "Equipe de teste",
            )
        app = create_app(
            Settings(
                database_url=url.set(host=url.host or "localhost").render_as_string(
                    hide_password=False
                ),
                app_env="test",
                privacy_notice_version="test-v1",
                privacy_notice_text="Teste de interface. Use apenas dados fictícios.",
                _env_file=None,
            )
        )

        def database():
            with Session(engine) as session:
                yield session

        app.dependency_overrides[get_session] = database
        uvicorn.run(app, host="127.0.0.1", port=8009, access_log=False)
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


if __name__ == "__main__":
    main()
