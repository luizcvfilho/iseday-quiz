"""initial schema

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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
        "quiz_versions",
        sa.Column("event_name", sa.Text(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'draft'"), nullable=False),
        sa.Column(
            "required_selection_count",
            sa.SmallInteger(),
            server_default=sa.text("25"),
            nullable=False,
        ),
        sa.Column(
            "scoring_method",
            sa.Text(),
            server_default=sa.text("'area_distinct_count_course_sum_v1'"),
            nullable=False,
        ),
        sa.Column("psychology_destination", sa.Text(), nullable=False),
        sa.Column("psychology_instructions", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(event_name) <> ''", name=op.f("ck_quiz_versions_event_name_nonempty")
        ),
        sa.CheckConstraint(
            "btrim(psychology_destination) <> ''",
            name=op.f("ck_quiz_versions_psychology_destination_nonempty"),
        ),
        sa.CheckConstraint(
            "btrim(psychology_instructions) <> ''",
            name=op.f("ck_quiz_versions_psychology_instructions_nonempty"),
        ),
        sa.CheckConstraint(
            "scoring_method = 'area_distinct_count_course_sum_v1'",
            name=op.f("ck_quiz_versions_scoring_method_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name=op.f("ck_quiz_versions_status_valid"),
        ),
        sa.CheckConstraint(
            "required_selection_count = 25", name=op.f("ck_quiz_versions_selection_count_fixed")
        ),
        sa.CheckConstraint(
            "version_number > 0", name=op.f("ck_quiz_versions_version_number_positive")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quiz_versions")),
        sa.UniqueConstraint("version_number", name=op.f("uq_quiz_versions_version_number")),
    )
    op.create_index(
        "uq_single_published_quiz",
        "quiz_versions",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'published'"),
    )
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
    op.create_index("ix_schools_name", "schools", [sa.literal_column("lower(name)")], unique=False)
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
        "areas",
        sa.Column("quiz_version_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("destination", sa.Text(), nullable=False),
        sa.Column("destination_instructions", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint("btrim(destination) <> ''", name=op.f("ck_areas_destination_nonempty")),
        sa.CheckConstraint(
            "btrim(destination_instructions) <> ''", name=op.f("ck_areas_instructions_nonempty")
        ),
        sa.CheckConstraint("btrim(name) <> ''", name=op.f("ck_areas_name_nonempty")),
        sa.ForeignKeyConstraint(
            ["quiz_version_id"],
            ["quiz_versions.id"],
            name=op.f("fk_areas_quiz_version_id_quiz_versions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_areas")),
        sa.UniqueConstraint("id", "quiz_version_id", name=op.f("uq_areas_id")),
        sa.UniqueConstraint("quiz_version_id", "name", name=op.f("uq_areas_quiz_version_id")),
    )
    op.create_table(
        "participations",
        sa.Column("quiz_version_id", sa.Uuid(), nullable=False),
        sa.Column("school_id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["quiz_version_id"],
            ["quiz_versions.id"],
            name=op.f("fk_participations_quiz_version_id_quiz_versions"),
        ),
        sa.ForeignKeyConstraint(
            ["school_id"], ["schools.id"], name=op.f("fk_participations_school_id_schools")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_participations")),
        sa.UniqueConstraint("access_token_hash", name=op.f("uq_participations_access_token_hash")),
        sa.UniqueConstraint("id", "quiz_version_id", name=op.f("uq_participations_id")),
    )
    op.create_index(
        "ix_participations_school",
        "participations",
        ["school_id", sa.literal_column("started_at DESC")],
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
    op.create_index(
        "ix_participations_version", "participations", ["quiz_version_id"], unique=False
    )
    op.create_table(
        "statements",
        sa.Column("quiz_version_id", sa.Uuid(), nullable=False),
        sa.Column("source_number", sa.SmallInteger(), nullable=False),
        sa.Column("display_order", sa.SmallInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint("btrim(text) <> ''", name=op.f("ck_statements_text_nonempty")),
        sa.CheckConstraint("display_order > 0", name=op.f("ck_statements_display_order_positive")),
        sa.CheckConstraint("source_number > 0", name=op.f("ck_statements_source_number_positive")),
        sa.ForeignKeyConstraint(
            ["quiz_version_id"],
            ["quiz_versions.id"],
            name=op.f("fk_statements_quiz_version_id_quiz_versions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_statements")),
        sa.UniqueConstraint("id", "quiz_version_id", name=op.f("uq_statements_id")),
        sa.UniqueConstraint("quiz_version_id", "display_order", name="uq_statements_version_order"),
        sa.UniqueConstraint(
            "quiz_version_id", "source_number", name="uq_statements_version_source"
        ),
    )
    op.create_table(
        "courses",
        sa.Column("quiz_version_id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["area_id", "quiz_version_id"],
            ["areas.id", "areas.quiz_version_id"],
            name=op.f("fk_courses_area_id_areas"),
        ),
        sa.ForeignKeyConstraint(
            ["quiz_version_id"],
            ["quiz_versions.id"],
            name=op.f("fk_courses_quiz_version_id_quiz_versions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_courses")),
        sa.UniqueConstraint("id", "quiz_version_id", name=op.f("uq_courses_id")),
        sa.UniqueConstraint("quiz_version_id", "name", name=op.f("uq_courses_quiz_version_id")),
    )
    op.create_index("ix_courses_area", "courses", ["area_id", "quiz_version_id"], unique=False)
    op.create_table(
        "participation_area_results",
        sa.Column("participation_id", sa.Uuid(), nullable=False),
        sa.Column("quiz_version_id", sa.Uuid(), nullable=False),
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
            ["area_id", "quiz_version_id"],
            ["areas.id", "areas.quiz_version_id"],
            name=op.f("fk_participation_area_results_area_id_areas"),
        ),
        sa.ForeignKeyConstraint(
            ["participation_id", "quiz_version_id"],
            ["participations.id", "participations.quiz_version_id"],
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
        sa.Column("quiz_version_id", sa.Uuid(), nullable=False),
        sa.Column("statement_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["participation_id", "quiz_version_id"],
            ["participations.id", "participations.quiz_version_id"],
            name=op.f("fk_participation_selections_participation_id_participations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["statement_id", "quiz_version_id"],
            ["statements.id", "statements.quiz_version_id"],
            name=op.f("fk_participation_selections_statement_id_statements"),
        ),
        sa.PrimaryKeyConstraint(
            "participation_id", "statement_id", name=op.f("pk_participation_selections")
        ),
    )
    op.create_table(
        "participation_course_results",
        sa.Column("participation_id", sa.Uuid(), nullable=False),
        sa.Column("quiz_version_id", sa.Uuid(), nullable=False),
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
            ["course_id", "quiz_version_id"],
            ["courses.id", "courses.quiz_version_id"],
            name=op.f("fk_participation_course_results_course_id_courses"),
        ),
        sa.ForeignKeyConstraint(
            ["participation_id", "quiz_version_id"],
            ["participations.id", "participations.quiz_version_id"],
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
        sa.Column("quiz_version_id", sa.Uuid(), nullable=False),
        sa.Column("statement_id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("weight", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint("weight > 0", name=op.f("ck_statement_course_weights_weight_positive")),
        sa.ForeignKeyConstraint(
            ["course_id", "quiz_version_id"],
            ["courses.id", "courses.quiz_version_id"],
            name=op.f("fk_statement_course_weights_course_id_courses"),
        ),
        sa.ForeignKeyConstraint(
            ["quiz_version_id"],
            ["quiz_versions.id"],
            name=op.f("fk_statement_course_weights_quiz_version_id_quiz_versions"),
        ),
        sa.ForeignKeyConstraint(
            ["statement_id", "quiz_version_id"],
            ["statements.id", "statements.quiz_version_id"],
            name=op.f("fk_statement_course_weights_statement_id_statements"),
        ),
        sa.PrimaryKeyConstraint(
            "statement_id", "course_id", name=op.f("pk_statement_course_weights")
        ),
    )
    op.create_index(
        "ix_weights_course",
        "statement_course_weights",
        ["course_id", "quiz_version_id"],
        unique=False,
    )
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
            "(agrees_with_result AND chosen_course_id IS NOT NULL) OR "
            "(NOT agrees_with_result AND chosen_course_id IS NULL)",
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

    op.execute(Path(__file__).with_name("0001_integrity.sql").read_text())


def downgrade() -> None:
    op.drop_table("participation_feedback")
    op.drop_index("ix_weights_course", table_name="statement_course_weights")
    op.drop_table("statement_course_weights")
    op.drop_index(
        "ix_course_recommendations",
        table_name="participation_course_results",
        postgresql_where=sa.text("is_recommended"),
    )
    op.drop_table("participation_course_results")
    op.drop_table("participation_selections")
    op.drop_index(
        "ix_area_winners",
        table_name="participation_area_results",
        postgresql_where=sa.text("is_winner"),
    )
    op.drop_table("participation_area_results")
    op.drop_index("ix_courses_area", table_name="courses")
    op.drop_table("courses")
    op.drop_table("statements")
    op.drop_index("ix_participations_version", table_name="participations")
    op.drop_index("ix_participations_status", table_name="participations")
    op.drop_index("ix_participations_started", table_name="participations")
    op.drop_index("ix_participations_school", table_name="participations")
    op.drop_table("participations")
    op.drop_table("areas")
    op.drop_index("ix_admin_sessions_user", table_name="admin_sessions")
    op.drop_table("admin_sessions")
    op.drop_index("ix_admin_audit_logs_created", table_name="admin_audit_logs")
    op.drop_table("admin_audit_logs")
    op.drop_index("ix_schools_name", table_name="schools")
    op.drop_table("schools")
    op.drop_index(
        "uq_single_published_quiz",
        table_name="quiz_versions",
        postgresql_where=sa.text("status = 'published'"),
    )
    op.drop_table("quiz_versions")
    op.drop_index("uq_admin_users_email", table_name="admin_users")
    op.drop_table("admin_users")
    # Dropping tables removes their triggers; remove the trigger functions too.
    for function in (
        "guard_feedback",
        "guard_participation_state",
        "guard_participation_children",
        "guard_quiz_version",
        "guard_weights_draft",
        "guard_catalog_draft",
    ):
        op.execute(f"DROP FUNCTION {function}()")
