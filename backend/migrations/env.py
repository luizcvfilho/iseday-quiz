from alembic import context
from sqlalchemy.engine import Connection

from app import models  # noqa: F401 -- register all domain tables with Base.metadata
from app.core.config import get_settings
from app.db import Base, build_engine

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=context.config.get_main_option("sqlalchemy.url") or str(get_settings().database_url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def migrate_connection(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Tests and maintenance commands can supply an isolated connection.
    if connection := context.config.attributes.get("connection"):
        migrate_connection(connection)
        return

    engine = build_engine(get_settings())
    try:
        with engine.connect() as connection:
            migrate_connection(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
