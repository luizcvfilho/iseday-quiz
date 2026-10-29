"""Real PostgreSQL tests, restricted to a *_test database and disposable schemas."""

import os
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def migration_config(connection):
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


@pytest.fixture(scope="session")
def postgres_url():
    value = os.environ.get("TEST_DATABASE_URL")
    if not value:
        if os.environ.get("REQUIRE_POSTGRES_TESTS") == "1":
            pytest.fail("TEST_DATABASE_URL is required for PostgreSQL checks")
        pytest.skip("Set TEST_DATABASE_URL or run scripts/check-db.sh for PostgreSQL checks")
    url = make_url(value)
    if url.drivername != "postgresql+psycopg" or not (url.database or "").endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must use postgresql+psycopg and a database ending in _test")
    return url


@contextmanager
def isolated_schema(url):
    schema = f"iseday_test_{uuid4().hex}"
    admin = create_engine(url)
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def empty_database(postgres_url):
    with isolated_schema(postgres_url) as engine:
        yield engine


@pytest.fixture(scope="session")
def migrated_database(postgres_url):
    with isolated_schema(postgres_url) as engine:
        with engine.begin() as connection:
            command.upgrade(migration_config(connection), "head")
        yield engine


@pytest.fixture
def db(migrated_database):
    with migrated_database.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()
