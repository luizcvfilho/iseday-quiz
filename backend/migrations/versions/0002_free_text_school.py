"""Store the school name on each participation, preserving existing history."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("participations", sa.Column("school_name", sa.Text(), nullable=True))
    # Completed/submitted history is immutable during normal application writes.
    # This transactional backfill only copies its existing school name.
    op.execute("ALTER TABLE participations DISABLE TRIGGER guard_participations")
    op.execute(
        "UPDATE participations p SET school_name = s.name FROM schools s WHERE s.id = p.school_id"
    )
    op.execute("ALTER TABLE participations ENABLE TRIGGER guard_participations")
    op.alter_column("participations", "school_name", nullable=False)
    op.create_check_constraint(
        op.f("ck_participations_school_name_nonempty"), "participations", "btrim(school_name) <> ''"
    )
    op.drop_index("ix_participations_school", table_name="participations")
    op.drop_constraint(
        op.f("fk_participations_school_id_schools"), "participations", type_="foreignkey"
    )
    op.drop_column("participations", "school_id")
    op.create_index(
        "ix_participations_school", "participations", ["school_name", sa.text("started_at DESC")]
    )
    op.drop_index("ix_schools_name", table_name="schools")
    op.drop_table("schools")


def downgrade():
    # Recreate one school per distinct saved name so participation history survives
    # rollback. Former school IDs, location and availability cannot be recovered.
    op.create_table(
        "schools",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("state_code", sa.String(length=2), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("btrim(name) <> ''", name=op.f("ck_schools_name_nonempty")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_schools")),
    )
    op.create_index("ix_schools_name", "schools", [sa.text("lower(name)")])
    op.execute("INSERT INTO schools (name) SELECT DISTINCT school_name FROM participations")
    op.add_column("participations", sa.Column("school_id", sa.Uuid(), nullable=True))
    op.execute("ALTER TABLE participations DISABLE TRIGGER guard_participations")
    op.execute(
        "UPDATE participations p SET school_id = s.id FROM schools s WHERE s.name = p.school_name"
    )
    op.execute("ALTER TABLE participations ENABLE TRIGGER guard_participations")
    op.alter_column("participations", "school_id", nullable=False)
    op.create_foreign_key(
        op.f("fk_participations_school_id_schools"),
        "participations",
        "schools",
        ["school_id"],
        ["id"],
    )
    op.drop_index("ix_participations_school", table_name="participations")
    op.drop_constraint(
        op.f("ck_participations_school_name_nonempty"), "participations", type_="check"
    )
    op.drop_column("participations", "school_name")
    op.create_index(
        "ix_participations_school", "participations", ["school_id", sa.text("started_at DESC")]
    )
