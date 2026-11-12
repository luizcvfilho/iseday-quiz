from collections.abc import Generator
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy import DateTime, MetaData, TypeDecorator, create_engine, func
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Session

from app.core.config import Settings


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class UTCDateTime(TypeDecorator):
    """MySQL DATETIME stores UTC without an offset; return aware values to the API."""

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(DATETIME(fsp=6))

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.utcoffset() is None:
            raise ValueError("Datetime must include a timezone")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect):
        return value.replace(tzinfo=UTC) if value is not None else None


def database_now():
    return func.utc_timestamp(6, type_=UTCDateTime())


def mysql_engine(url: str | URL):
    return create_engine(
        url,
        isolation_level="READ COMMITTED",
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3, "charset": "utf8mb4"},
        hide_parameters=True,
    )


def build_engine(settings: Settings):
    return mysql_engine(str(settings.database_url))


def get_session(request: Request) -> Generator[Session]:
    with Session(request.app.state.engine) as session:
        yield session
