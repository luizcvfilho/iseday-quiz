"""Replace quiz versions and test participations with one fixed, preloaded catalog.

This intentionally deletes the old test participations, selections, results and
feedback. Administrator accounts, sessions and audit records are preserved.
"""

import json
from pathlib import Path
from uuid import UUID, uuid5

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

CATALOG_NAMESPACE = UUID("3cc0ba4e-e328-4e57-b5ee-b01568c47758")


def upgrade():
    for function in (
        "guard_feedback",
        "guard_participation_state",
        "guard_participation_children",
        "guard_quiz_version",
        "guard_weights_draft",
        "guard_catalog_draft",
    ):
        op.execute(f"DROP FUNCTION {function}() CASCADE")
    for table in (
        "participation_feedback",
        "participation_course_results",
        "participation_area_results",
        "participation_selections",
        "participations",
        "statement_course_weights",
        "statements",
        "courses",
        "areas",
        "quiz_versions",
    ):
        op.drop_table(table)
    op.execute(Path(__file__).with_suffix(".sql").read_text(encoding="utf-8"))
    report = json.loads(
        (Path(__file__).resolve().parents[2] / "catalog" / "quiz-final.json").read_text(
            encoding="utf-8"
        )
    )

    def identifier(kind, key):
        return uuid5(CATALOG_NAMESPACE, f"{kind}:{key}")

    areas = sa.table(
        "areas",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.Text()),
        sa.column("destination", sa.Text()),
        sa.column("destination_instructions", sa.Text()),
    )
    courses = sa.table(
        "courses",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.Text()),
        sa.column("area_id", sa.Uuid()),
    )
    statements = sa.table(
        "statements",
        sa.column("id", sa.Uuid()),
        sa.column("source_number", sa.SmallInteger()),
        sa.column("display_order", sa.SmallInteger()),
        sa.column("text", sa.Text()),
    )
    weights = sa.table(
        "statement_course_weights",
        sa.column("statement_id", sa.Uuid()),
        sa.column("course_id", sa.Uuid()),
        sa.column("weight", sa.SmallInteger()),
    )
    op.bulk_insert(
        areas,
        [
            dict(
                id=identifier("area", a["name"]),
                name=a["name"],
                destination=a["destination"],
                destination_instructions=report["area_destination_instructions"],
            )
            for a in report["areas"]
        ],
    )
    op.bulk_insert(
        courses,
        [
            dict(
                id=identifier("course", c["name"]),
                name=c["name"],
                area_id=identifier("area", c["area"]),
            )
            for c in report["courses"]
        ],
    )
    op.bulk_insert(
        statements,
        [
            dict(
                id=identifier("statement", s["source_number"]),
                source_number=s["source_number"],
                display_order=s["display_order"],
                text=s["text"],
            )
            for s in report["statements"]
        ],
    )
    op.bulk_insert(
        weights,
        [
            dict(
                statement_id=identifier("statement", s["source_number"]),
                course_id=identifier("course", name),
                weight=1,
            )
            for s in report["statements"]
            for name in s["courses"]
        ],
    )
    op.execute("""
        CREATE FUNCTION guard_fixed_catalog() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'The quiz catalog is fixed and cannot be changed';
        END;
        $$;
    """)
    for table in ("areas", "courses", "statements", "statement_course_weights"):
        op.execute(f"""
            CREATE TRIGGER guard_fixed_{table}
            BEFORE INSERT OR UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION guard_fixed_catalog();
            CREATE TRIGGER guard_truncate_{table}
            BEFORE TRUNCATE ON {table}
            FOR EACH STATEMENT EXECUTE FUNCTION guard_fixed_catalog();
        """)


def downgrade():
    raise RuntimeError(
        "A migração 0003 remove dados de teste e o modelo de versões. "
        "Para retornar ao modelo anterior, restaure um backup anterior à migração."
    )
