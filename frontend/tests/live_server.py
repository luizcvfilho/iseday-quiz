"""Browser-test API with a disposable schema in an explicitly named *_test database."""

import os
import re
from pathlib import Path
from uuid import uuid4

import uvicorn
from alembic import command
from alembic.config import Config
from app.admin.__main__ import save_account
from app.core.config import Settings
from app.db import mysql_engine
from app.main import create_app
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


def main():
    value = os.environ.get("TEST_DATABASE_URL", "")
    if not value:
        raise SystemExit("TEST_DATABASE_URL is required for browser integration checks")
    url = make_url(value)
    if url.drivername != "mysql+pymysql" or not re.fullmatch(
        r"[a-zA-Z0-9_]{0,24}_test", url.database or ""
    ):
        raise SystemExit(
            "Use mysql+pymysql and a database ending in _test (up to 29 characters)"
        )
    schema = f"{url.database}_{uuid4().hex}"
    isolated_url = url.set(database=schema)
    admin = mysql_engine(url)
    engine = mysql_engine(isolated_url)
    try:
        with admin.begin() as connection:
            connection.execute(
                text(
                    f"CREATE DATABASE `{schema}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin"
                )
            )
        with engine.begin() as connection:
            config = Config(
                str(Path(__file__).resolve().parents[2] / "backend" / "alembic.ini")
            )
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
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
                database_url=isolated_url.render_as_string(hide_password=False),
                app_env="test",
                privacy_notice_version="test-v1",
                privacy_notice_text="Teste de interface. Use apenas dados fictícios.",
                _env_file=None,
            )
        )

        uvicorn.run(app, host="127.0.0.1", port=8009, access_log=False)
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS `{schema}`"))
        admin.dispose()


if __name__ == "__main__":
    main()
