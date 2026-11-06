"""Create the current quiz schema and install the fixed catalog.

Revision ID: 0001
Revises:
"""

import json
from pathlib import Path
from uuid import UUID, uuid5

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

CATALOG_NAMESPACE = UUID("3cc0ba4e-e328-4e57-b5ee-b01568c47758")


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("btrim(email) <> ''", name=op.f("ck_admin_users_email_nonempty")),
        sa.CheckConstraint("btrim(name) <> ''", name=op.f("ck_admin_users_name_nonempty")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_users")),
    )
    op.create_index(
        "uq_admin_users_email", "admin_users", [sa.literal_column("lower(email)")], unique=True
    )
    op.create_table(
        "areas",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("destination", sa.Text(), nullable=False),
        sa.Column("destination_instructions", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint("btrim(destination) <> ''", name=op.f("ck_areas_destination_nonempty")),
        sa.CheckConstraint(
            "btrim(destination_instructions) <> ''", name=op.f("ck_areas_instructions_nonempty")
        ),
        sa.CheckConstraint("btrim(name) <> ''", name=op.f("ck_areas_name_nonempty")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_areas")),
        sa.UniqueConstraint("name", name=op.f("uq_areas_name")),
    )
    op.create_table(
        "participations",
        sa.Column("school_name", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("phone", sa.String(length=14), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("privacy_notice_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("access_token_hash", sa.Text(), nullable=True),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "(status = 'completed') = (completed_at IS NOT NULL)",
            name=op.f("ck_participations_completion_timestamp_matches_status"),
        ),
        sa.CheckConstraint(
            "(status = 'draft' AND submitted_at IS NULL) OR "
            "(status IN ('submitted', 'completed') AND submitted_at IS NOT NULL)",
            name=op.f("ck_participations_submission_timestamp_matches_status"),
        ),
        sa.CheckConstraint(
            "access_token_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_participations_token_hash_format")
        ),
        sa.CheckConstraint("btrim(email) <> ''", name=op.f("ck_participations_email_nonempty")),
        sa.CheckConstraint(
            "btrim(full_name) <> ''", name=op.f("ck_participations_full_name_nonempty")
        ),
        sa.CheckConstraint(
            "btrim(privacy_notice_version) <> ''",
            name=op.f("ck_participations_privacy_notice_nonempty"),
        ),
        sa.CheckConstraint(
            "btrim(school_name) <> ''", name=op.f("ck_participations_school_name_nonempty")
        ),
        sa.CheckConstraint(
            "phone ~ '^\\+55[1-9][0-9][0-9]{8,9}$'", name=op.f("ck_participations_phone_format")
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'submitted', 'completed')",
            name=op.f("ck_participations_status_valid"),
        ),
        sa.CheckConstraint(
            "access_expires_at > started_at", name=op.f("ck_participations_expiry_after_start")
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= submitted_at",
            name=op.f("ck_participations_completion_after_submission"),
        ),
        sa.CheckConstraint(
            "submitted_at IS NULL OR submitted_at >= started_at",
            name=op.f("ck_participations_submission_after_start"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_participations")),
        sa.UniqueConstraint("access_token_hash", name=op.f("uq_participations_access_token_hash")),
    )
    op.create_index(
        "ix_participations_school",
        "participations",
        ["school_name", sa.literal_column("started_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_participations_started",
        "participations",
        [sa.literal_column("started_at DESC"), "id"],
        unique=False,
    )
    op.create_index(
        "ix_participations_status",
        "participations",
        ["status", sa.literal_column("started_at DESC")],
        unique=False,
    )
    op.create_table(
        "statements",
        sa.Column("source_number", sa.SmallInteger(), nullable=False),
        sa.Column("display_order", sa.SmallInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint("btrim(text) <> ''", name=op.f("ck_statements_text_nonempty")),
        sa.CheckConstraint("display_order > 0", name=op.f("ck_statements_display_order_positive")),
        sa.CheckConstraint("source_number > 0", name=op.f("ck_statements_source_number_positive")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_statements")),
        sa.UniqueConstraint("display_order", name=op.f("uq_statements_display_order")),
        sa.UniqueConstraint("source_number", name=op.f("uq_statements_source_number")),
    )
    op.create_table(
        "admin_audit_logs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("admin_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_participation_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("btrim(action) <> ''", name=op.f("ck_admin_audit_logs_action_nonempty")),
        sa.ForeignKeyConstraint(
            ["admin_user_id"],
            ["admin_users.id"],
            name=op.f("fk_admin_audit_logs_admin_user_id_admin_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_audit_logs")),
    )
    op.create_index(
        "ix_admin_audit_logs_created",
        "admin_audit_logs",
        [sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_table(
        "admin_sessions",
        sa.Column("admin_user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "token_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_admin_sessions_token_hash_format")
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name=op.f("ck_admin_sessions_expiry_after_creation")
        ),
        sa.ForeignKeyConstraint(
            ["admin_user_id"],
            ["admin_users.id"],
            name=op.f("fk_admin_sessions_admin_user_id_admin_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_admin_sessions_token_hash")),
    )
    op.create_index("ix_admin_sessions_user", "admin_sessions", ["admin_user_id"], unique=False)
    op.create_table(
        "courses",
        sa.Column("area_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("destination", sa.Text(), nullable=True),
        sa.Column("destination_instructions", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "(destination IS NULL AND destination_instructions IS NULL) OR "
            "(destination IS NOT NULL AND btrim(destination) <> '' AND "
            "destination_instructions IS NOT NULL AND btrim(destination_instructions) <> '')",
            name=op.f("ck_courses_destination_pair"),
        ),
        sa.CheckConstraint("btrim(name) <> ''", name=op.f("ck_courses_name_nonempty")),
        sa.ForeignKeyConstraint(["area_id"], ["areas.id"], name=op.f("fk_courses_area_id_areas")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_courses")),
        sa.UniqueConstraint("name", name=op.f("uq_courses_name")),
    )
    op.create_index("ix_courses_area", "courses", ["area_id"], unique=False)
    op.create_table(
        "participation_area_results",
        sa.Column("participation_id", sa.Uuid(), nullable=False),
        sa.Column("area_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.Column("is_winner", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "NOT is_winner OR score > 0", name=op.f("ck_participation_area_results_winner_positive")
        ),
        sa.CheckConstraint(
            "score BETWEEN 0 AND 25", name=op.f("ck_participation_area_results_score_range")
        ),
        sa.ForeignKeyConstraint(
            ["area_id"], ["areas.id"], name=op.f("fk_participation_area_results_area_id_areas")
        ),
        sa.ForeignKeyConstraint(
            ["participation_id"],
            ["participations.id"],
            name=op.f("fk_participation_area_results_participation_id_participations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "participation_id", "area_id", name=op.f("pk_participation_area_results")
        ),
    )
    op.create_index(
        "ix_area_winners",
        "participation_area_results",
        ["area_id", "participation_id"],
        unique=False,
        postgresql_where=sa.text("is_winner"),
    )
    op.create_table(
        "participation_selections",
        sa.Column("participation_id", sa.Uuid(), nullable=False),
        sa.Column("statement_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["participation_id"],
            ["participations.id"],
            name=op.f("fk_participation_selections_participation_id_participations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["statement_id"],
            ["statements.id"],
            name=op.f("fk_participation_selections_statement_id_statements"),
        ),
        sa.PrimaryKeyConstraint(
            "participation_id", "statement_id", name=op.f("pk_participation_selections")
        ),
    )
    op.create_table(
        "participation_course_results",
        sa.Column("participation_id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("is_recommended", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "NOT is_recommended OR score > 0",
            name=op.f("ck_participation_course_results_recommended_positive"),
        ),
        sa.CheckConstraint(
            "score >= 0", name=op.f("ck_participation_course_results_score_nonnegative")
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_participation_course_results_course_id_courses"),
        ),
        sa.ForeignKeyConstraint(
            ["participation_id"],
            ["participations.id"],
            name=op.f("fk_participation_course_results_participation_id_participations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "participation_id", "course_id", name=op.f("pk_participation_course_results")
        ),
    )
    op.create_index(
        "ix_course_recommendations",
        "participation_course_results",
        ["course_id", "participation_id"],
        unique=False,
        postgresql_where=sa.text("is_recommended"),
    )
    op.create_table(
        "statement_course_weights",
        sa.Column("statement_id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("weight", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint("weight > 0", name=op.f("ck_statement_course_weights_weight_positive")),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_statement_course_weights_course_id_courses"),
        ),
        sa.ForeignKeyConstraint(
            ["statement_id"],
            ["statements.id"],
            name=op.f("fk_statement_course_weights_statement_id_statements"),
        ),
        sa.PrimaryKeyConstraint(
            "statement_id", "course_id", name=op.f("pk_statement_course_weights")
        ),
    )
    op.create_index("ix_weights_course", "statement_course_weights", ["course_id"], unique=False)
    op.create_table(
        "participation_feedback",
        sa.Column("participation_id", sa.Uuid(), nullable=False),
        sa.Column("agrees_with_result", sa.Boolean(), nullable=False),
        sa.Column("chosen_course_id", sa.Uuid(), nullable=True),
        sa.Column("destination", sa.Text(), nullable=False),
        sa.Column("destination_instructions", sa.Text(), nullable=False),
        sa.Column(
            "answered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(destination) <> ''", name=op.f("ck_participation_feedback_destination_nonempty")
        ),
        sa.CheckConstraint(
            "btrim(destination_instructions) <> ''",
            name=op.f("ck_participation_feedback_instructions_nonempty"),
        ),
        sa.CheckConstraint(
            "agrees_with_result OR chosen_course_id IS NULL",
            name=op.f("ck_participation_feedback_agreement_matches_course"),
        ),
        sa.ForeignKeyConstraint(
            ["participation_id", "chosen_course_id"],
            [
                "participation_course_results.participation_id",
                "participation_course_results.course_id",
            ],
            name=op.f("fk_participation_feedback_participation_id_participation_course_results"),
        ),
        sa.ForeignKeyConstraint(
            ["participation_id"],
            ["participations.id"],
            name=op.f("fk_participation_feedback_participation_id_participations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("participation_id", name=op.f("pk_participation_feedback")),
    )

    op.execute(Path(__file__).with_name("0001_integrity.sql").read_text(encoding="utf-8"))
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


def downgrade() -> None:
    op.drop_table("participation_feedback")
    op.drop_table("statement_course_weights")
    op.drop_table("participation_course_results")
    op.drop_table("participation_selections")
    op.drop_table("participation_area_results")
    op.drop_table("courses")
    op.drop_table("admin_sessions")
    op.drop_table("admin_audit_logs")
    op.drop_table("statements")
    op.drop_table("participations")
    op.drop_table("areas")
    op.drop_table("admin_users")
    # Dropping tables removes their triggers; remove the trigger functions too.
    for function in (
        "guard_fixed_catalog",
        "guard_feedback",
        "guard_participation_state",
        "guard_participation_children",
    ):
        op.execute(f"DROP FUNCTION {function}()")
