import pytest
from alembic import command
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalog import DEFAULT_WORKBOOK, read_catalog
from app.models import Area, Course, Statement, StatementCourseWeight
from app.participants.service import load_scoring_catalog
from app.scoring import calculate_scores

from .conftest import migration_config

pytestmark = pytest.mark.mysql


def test_migration_installs_the_fixed_catalog_and_repeated_upgrade_keeps_it(empty_database):
    with empty_database.begin() as connection:
        config = migration_config(connection)
        command.upgrade(config, "head")
        before = connection.scalars(select(Statement.id).order_by(Statement.display_order)).all()
        command.upgrade(config, "head")
        assert (
            connection.scalars(select(Statement.id).order_by(Statement.display_order)).all()
            == before
        )
        for model, count in ((Area, 5), (Course, 9), (Statement, 74), (StatementCourseWeight, 78)):
            assert connection.scalar(select(func.count()).select_from(model)) == count
        source = read_catalog(DEFAULT_WORKBOOK)
        assert connection.scalars(select(Course.name).order_by(Course.name)).all() == [
            c.name for c in source.courses
        ]
        assert connection.scalars(
            select(Statement.text).order_by(Statement.source_number)
        ).all() == [s.text for s in source.statements]
        with Session(connection) as session:
            scores = calculate_scores(load_scoring_catalog(session), before[:25])
            recommended = {s.course_id: s.score for s in scores.courses if s.is_recommended}
            assert len(recommended) == 1
            name = session.scalar(select(Course.name).where(Course.id.in_(recommended)))
            assert name == "Enfermagem e Fisioterapia"
            assert list(recommended.values()) == [8]
