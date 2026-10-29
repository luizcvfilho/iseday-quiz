from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from alembic import command
from sqlalchemy import event, func, select, update

from app.catalog import DEFAULT_WORKBOOK, CatalogError, import_catalog, read_catalog
from app.models import Area, Course, QuizVersion, Statement, StatementCourseWeight

from .conftest import migration_config

pytestmark = pytest.mark.postgres


@pytest.fixture
def catalog_database(empty_database):
    with empty_database.begin() as connection:
        command.upgrade(migration_config(connection), "head")
    return empty_database


def counts(engine):
    with engine.connect() as connection:
        return [
            connection.scalar(select(func.count()).select_from(model))
            for model in (
                QuizVersion,
                Area,
                Course,
                Statement,
                StatementCourseWeight,
            )
        ]


def test_import_roundtrip_idempotence_and_preserved_published_version(catalog_database):
    engine = catalog_database
    catalog = read_catalog(DEFAULT_WORKBOOK)
    first = import_catalog(engine, catalog, version_number=1)
    assert first.created and first.status == "draft"
    assert counts(engine) == [1, 5, 11, 74, 96]
    again = import_catalog(engine, catalog, version_number=1)
    assert not again.created and again.version_id == first.version_id
    with engine.begin() as connection:
        assert connection.scalar(select(QuizVersion.status)) == "draft"
        assert connection.scalars(
            select(Statement.text).order_by(Statement.source_number)
        ).all() == [statement.text for statement in catalog.statements]
        assert set(connection.scalars(select(StatementCourseWeight.weight))) == {1}
        assert (
            connection.scalar(
                select(func.count()).select_from(Course).where(Course.destination.is_not(None))
            )
            == 0
        )
        connection.execute(update(QuizVersion).values(status="published"))
    published = import_catalog(engine, catalog, version_number=1)
    assert not published.created and published.status == "published"
    assert counts(engine) == [1, 5, 11, 74, 96]


def test_conflict_never_replaces_content_and_new_version_has_new_ids(catalog_database):
    engine = catalog_database
    catalog = read_catalog(DEFAULT_WORKBOOK)
    first = import_catalog(engine, catalog, version_number=1)
    changed = replace(
        catalog,
        statements=(
            replace(catalog.statements[0], text="Texto revisado"),
            *catalog.statements[1:],
        ),
    )
    with pytest.raises(CatalogError, match="conteúdo diferente"):
        import_catalog(engine, changed, version_number=1)
    with pytest.raises(CatalogError, match="conteúdo diferente"):
        import_catalog(engine, catalog, version_number=1, event_name="Outro evento")
    assert counts(engine) == [1, 5, 11, 74, 96]
    second = import_catalog(engine, changed, version_number=2)
    assert second.created and second.version_id != first.version_id
    assert counts(engine) == [2, 10, 22, 148, 192]


def test_detects_modified_weights_not_just_counts(catalog_database):
    engine = catalog_database
    catalog = read_catalog(DEFAULT_WORKBOOK)
    import_catalog(engine, catalog, version_number=1)
    with engine.begin() as connection:
        connection.execute(update(StatementCourseWeight).values(weight=2))
    with pytest.raises(CatalogError, match="conteúdo diferente"):
        import_catalog(engine, catalog, version_number=1)


def test_failure_after_partial_inserts_rolls_back_everything(catalog_database):
    engine = catalog_database

    def fail_course_insert(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO courses"):
            raise RuntimeError("Simulated failure after version and areas were inserted")

    event.listen(engine, "before_cursor_execute", fail_course_insert)
    try:
        with pytest.raises(RuntimeError, match="Simulated failure"):
            import_catalog(engine, read_catalog(DEFAULT_WORKBOOK), version_number=1)
    finally:
        event.remove(engine, "before_cursor_execute", fail_course_insert)
    assert counts(engine) == [0, 0, 0, 0, 0]


def test_concurrent_identical_imports_create_one_draft(catalog_database):
    engine = catalog_database
    catalog = read_catalog(DEFAULT_WORKBOOK)
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [
            workers.submit(import_catalog, engine, catalog, version_number=1) for _ in range(2)
        ]
        results = [future.result(timeout=15) for future in futures]
    assert sorted(result.created for result in results) == [False, True]
    assert results[0].version_id == results[1].version_id
    assert counts(engine) == [1, 5, 11, 74, 96]
