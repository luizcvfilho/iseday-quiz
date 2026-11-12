"""Real MySQL tests, restricted to a *_test database and disposable schemas."""

import os
import re
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.db import mysql_engine

from .helpers import catalog


def migration_config(connection):
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


@pytest.fixture(scope="session")
def mysql_url():
    value = os.environ.get("TEST_DATABASE_URL")
    if not value:
        if os.environ.get("REQUIRE_MYSQL_TESTS") == "1":
            pytest.fail("TEST_DATABASE_URL is required for MySQL checks")
        pytest.skip("Set TEST_DATABASE_URL or run scripts/check-db.sh for MySQL checks")
    url = make_url(value)
    if url.drivername != "mysql+pymysql" or not re.fullmatch(
        r"[a-zA-Z0-9_]{0,24}_test", url.database or ""
    ):
        pytest.fail(
            "TEST_DATABASE_URL must use mysql+pymysql and a database ending in _test "
            "(up to 29 letters, digits or underscores)"
        )
    return url


@contextmanager
def isolated_schema(url):
    schema = f"{url.database}_{uuid4().hex}"
    admin = mysql_engine(url)
    engine = mysql_engine(url.set(database=schema))
    try:
        with admin.begin() as connection:
            connection.execute(
                text(f"CREATE DATABASE `{schema}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin")
            )
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS `{schema}`"))
        admin.dispose()


@pytest.fixture
def empty_database(mysql_url):
    with isolated_schema(mysql_url) as engine:
        yield engine


@pytest.fixture(scope="session")
def migrated_database(mysql_url):
    with isolated_schema(mysql_url) as engine:
        with engine.begin() as connection:
            command.upgrade(migration_config(connection), "head")
        yield engine, catalog(engine)


@pytest.fixture
def quiz(migrated_database):
    return migrated_database[1]


@pytest.fixture
def db(migrated_database):
    with migrated_database[0].connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()
