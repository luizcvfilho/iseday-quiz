"""Persistent quiz domain. Schema changes are applied exclusively through Alembic."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class UUIDPrimaryKey:
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))


class CreatedAt:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdminUser(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "admin_users"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="name_nonempty"),
        CheckConstraint("btrim(email) <> ''", name="email_nonempty"),
        Index("uq_admin_users_email", func.lower(text("email")), unique=True),
    )

    name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))


class AdminSession(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "admin_sessions"
    __table_args__ = (
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="token_hash_format"),
        CheckConstraint("expires_at > created_at", name="expiry_after_creation"),
        Index("ix_admin_sessions_user", "admin_user_id"),
    )

    admin_user_id: Mapped[UUID] = mapped_column(ForeignKey("admin_users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Area(UUIDPrimaryKey, Base):
    __tablename__ = "areas"
    __table_args__ = (
        UniqueConstraint("name"),
        CheckConstraint("btrim(name) <> ''", name="name_nonempty"),
        CheckConstraint("btrim(destination) <> ''", name="destination_nonempty"),
        CheckConstraint("btrim(destination_instructions) <> ''", name="instructions_nonempty"),
    )

    name: Mapped[str] = mapped_column(Text)
    destination: Mapped[str] = mapped_column(Text)
    destination_instructions: Mapped[str] = mapped_column(Text)


class Course(UUIDPrimaryKey, Base):
    __tablename__ = "courses"
    __table_args__ = (
        UniqueConstraint("name"),
        CheckConstraint("btrim(name) <> ''", name="name_nonempty"),
        CheckConstraint(
            "(destination IS NULL AND destination_instructions IS NULL) OR "
            "(destination IS NOT NULL AND btrim(destination) <> '' AND "
            "destination_instructions IS NOT NULL AND btrim(destination_instructions) <> '')",
            name="destination_pair",
        ),
        Index("ix_courses_area", "area_id"),
    )

    area_id: Mapped[UUID] = mapped_column(ForeignKey("areas.id"))
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    destination: Mapped[str | None] = mapped_column(Text)
    destination_instructions: Mapped[str | None] = mapped_column(Text)


class Statement(UUIDPrimaryKey, Base):
    __tablename__ = "statements"
    __table_args__ = (
        UniqueConstraint("source_number"),
        UniqueConstraint("display_order"),
        CheckConstraint("source_number > 0", name="source_number_positive"),
        CheckConstraint("display_order > 0", name="display_order_positive"),
        CheckConstraint("btrim(text) <> ''", name="text_nonempty"),
    )

    source_number: Mapped[int] = mapped_column(SmallInteger)
    display_order: Mapped[int] = mapped_column(SmallInteger)
    text: Mapped[str] = mapped_column(Text)


class StatementCourseWeight(Base):
    __tablename__ = "statement_course_weights"
    __table_args__ = (
        CheckConstraint("weight > 0", name="weight_positive"),
        Index("ix_weights_course", "course_id"),
    )

    statement_id: Mapped[UUID] = mapped_column(ForeignKey("statements.id"), primary_key=True)
    course_id: Mapped[UUID] = mapped_column(ForeignKey("courses.id"), primary_key=True)
    weight: Mapped[int] = mapped_column(SmallInteger, server_default=text("1"))


class Participation(UUIDPrimaryKey, Base):
    __tablename__ = "participations"
    __table_args__ = (
        CheckConstraint("btrim(school_name) <> ''", name="school_name_nonempty"),
        CheckConstraint("btrim(full_name) <> ''", name="full_name_nonempty"),
        CheckConstraint(r"phone ~ '^\+55[1-9][0-9][0-9]{8,9}$'", name="phone_format"),
        CheckConstraint("btrim(email) <> ''", name="email_nonempty"),
        CheckConstraint("btrim(privacy_notice_version) <> ''", name="privacy_notice_nonempty"),
        CheckConstraint("status IN ('draft', 'submitted', 'completed')", name="status_valid"),
        CheckConstraint("access_token_hash ~ '^[0-9a-f]{64}$'", name="token_hash_format"),
        CheckConstraint(
            "(status = 'draft' AND submitted_at IS NULL) OR "
            "(status IN ('submitted', 'completed') AND submitted_at IS NOT NULL)",
            name="submission_timestamp_matches_status",
        ),
        CheckConstraint(
            "(status = 'completed') = (completed_at IS NOT NULL)",
            name="completion_timestamp_matches_status",
        ),
        CheckConstraint("access_expires_at > started_at", name="expiry_after_start"),
        CheckConstraint(
            "submitted_at IS NULL OR submitted_at >= started_at", name="submission_after_start"
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= submitted_at",
            name="completion_after_submission",
        ),
        Index("ix_participations_started", text("started_at DESC"), "id"),
        Index("ix_participations_school", "school_name", text("started_at DESC")),
        Index("ix_participations_status", "status", text("started_at DESC")),
    )

    school_name: Mapped[str] = mapped_column(Text)
    full_name: Mapped[str] = mapped_column(Text)
    phone: Mapped[str] = mapped_column(String(14))
    email: Mapped[str] = mapped_column(Text)
    privacy_notice_version: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'draft'"))
    access_token_hash: Mapped[str | None] = mapped_column(Text, unique=True)
    access_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ParticipationSelection(Base):
    __tablename__ = "participation_selections"

    participation_id: Mapped[UUID] = mapped_column(
        ForeignKey("participations.id", ondelete="CASCADE"), primary_key=True
    )
    statement_id: Mapped[UUID] = mapped_column(ForeignKey("statements.id"), primary_key=True)


class ParticipationAreaResult(Base):
    __tablename__ = "participation_area_results"
    __table_args__ = (
        CheckConstraint("score BETWEEN 0 AND 25", name="score_range"),
        CheckConstraint("NOT is_winner OR score > 0", name="winner_positive"),
        Index("ix_area_winners", "area_id", "participation_id", postgresql_where=text("is_winner")),
    )

    participation_id: Mapped[UUID] = mapped_column(
        ForeignKey("participations.id", ondelete="CASCADE"), primary_key=True
    )
    area_id: Mapped[UUID] = mapped_column(ForeignKey("areas.id"), primary_key=True)
    score: Mapped[int] = mapped_column(SmallInteger)
    is_winner: Mapped[bool]


class ParticipationCourseResult(Base):
    __tablename__ = "participation_course_results"
    __table_args__ = (
        CheckConstraint("score >= 0", name="score_nonnegative"),
        CheckConstraint("NOT is_recommended OR score > 0", name="recommended_positive"),
        Index(
            "ix_course_recommendations",
            "course_id",
            "participation_id",
            postgresql_where=text("is_recommended"),
        ),
    )

    participation_id: Mapped[UUID] = mapped_column(
        ForeignKey("participations.id", ondelete="CASCADE"), primary_key=True
    )
    course_id: Mapped[UUID] = mapped_column(ForeignKey("courses.id"), primary_key=True)
    score: Mapped[int]
    is_recommended: Mapped[bool]


class ParticipationFeedback(Base):
    __tablename__ = "participation_feedback"
    __table_args__ = (
        ForeignKeyConstraint(
            ["participation_id", "chosen_course_id"],
            [
                "participation_course_results.participation_id",
                "participation_course_results.course_id",
            ],
        ),
        CheckConstraint("btrim(destination) <> ''", name="destination_nonempty"),
        CheckConstraint("btrim(destination_instructions) <> ''", name="instructions_nonempty"),
        CheckConstraint(
            "agrees_with_result OR chosen_course_id IS NULL",
            name="agreement_matches_course",
        ),
    )

    participation_id: Mapped[UUID] = mapped_column(
        ForeignKey("participations.id", ondelete="CASCADE"), primary_key=True
    )
    agrees_with_result: Mapped[bool]
    chosen_course_id: Mapped[UUID | None]
    destination: Mapped[str] = mapped_column(Text)
    destination_instructions: Mapped[str] = mapped_column(Text)
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AdminAuditLog(CreatedAt, Base):
    __tablename__ = "admin_audit_logs"
    __table_args__ = (
        CheckConstraint("btrim(action) <> ''", name="action_nonempty"),
        Index("ix_admin_audit_logs_created", text("created_at DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    admin_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(Text)
    # Audit records survive controlled deletion of a participation.
    target_participation_id: Mapped[UUID | None]
