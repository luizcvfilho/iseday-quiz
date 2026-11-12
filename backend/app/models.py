"""Persistent quiz domain. Schema changes are applied exclusively through Alembic."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime

MYSQL_TABLE = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_bin",
}


class UUIDPrimaryKey:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)


class CreatedAt:
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=text("(UTC_TIMESTAMP(6))")
    )


class AdminUser(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "admin_users"
    __table_args__ = (
        CheckConstraint("is_active IN (0, 1)", name="is_active_boolean"),
        CheckConstraint("trim(name) <> ''", name="name_nonempty"),
        CheckConstraint("trim(email) <> ''", name="email_nonempty"),
        UniqueConstraint("email"),
        MYSQL_TABLE,
    )

    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(254, collation="utf8mb4_0900_as_ci"))
    password_hash: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(server_default=text("1"))


class AdminSession(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "admin_sessions"
    __table_args__ = (
        CheckConstraint("token_hash REGEXP '^[0-9a-f]{64}$'", name="token_hash_format"),
        CheckConstraint("expires_at > created_at", name="expiry_after_creation"),
        Index("ix_admin_sessions_user", "admin_user_id"),
        MYSQL_TABLE,
    )

    admin_user_id: Mapped[UUID] = mapped_column(ForeignKey("admin_users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class Area(UUIDPrimaryKey, Base):
    __tablename__ = "areas"
    __table_args__ = (
        UniqueConstraint("name"),
        CheckConstraint("trim(name) <> ''", name="name_nonempty"),
        CheckConstraint("trim(destination) <> ''", name="destination_nonempty"),
        CheckConstraint("trim(destination_instructions) <> ''", name="instructions_nonempty"),
        MYSQL_TABLE,
    )

    name: Mapped[str] = mapped_column(String(255))
    destination: Mapped[str] = mapped_column(Text)
    destination_instructions: Mapped[str] = mapped_column(Text)


class Course(UUIDPrimaryKey, Base):
    __tablename__ = "courses"
    __table_args__ = (
        UniqueConstraint("name"),
        CheckConstraint("trim(name) <> ''", name="name_nonempty"),
        CheckConstraint(
            "(destination IS NULL AND destination_instructions IS NULL) OR "
            "(destination IS NOT NULL AND trim(destination) <> '' AND "
            "destination_instructions IS NOT NULL AND trim(destination_instructions) <> '')",
            name="destination_pair",
        ),
        Index("ix_courses_area", "area_id"),
        MYSQL_TABLE,
    )

    area_id: Mapped[UUID] = mapped_column(ForeignKey("areas.id"))
    name: Mapped[str] = mapped_column(String(255))
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
        CheckConstraint("trim(text) <> ''", name="text_nonempty"),
        MYSQL_TABLE,
    )

    source_number: Mapped[int] = mapped_column(SmallInteger)
    display_order: Mapped[int] = mapped_column(SmallInteger)
    text: Mapped[str] = mapped_column(Text)


class StatementCourseWeight(Base):
    __tablename__ = "statement_course_weights"
    __table_args__ = (
        CheckConstraint("weight > 0", name="weight_positive"),
        Index("ix_weights_course", "course_id"),
        MYSQL_TABLE,
    )

    statement_id: Mapped[UUID] = mapped_column(ForeignKey("statements.id"), primary_key=True)
    course_id: Mapped[UUID] = mapped_column(ForeignKey("courses.id"), primary_key=True)
    weight: Mapped[int] = mapped_column(SmallInteger, server_default=text("1"))


class Participation(UUIDPrimaryKey, Base):
    __tablename__ = "participations"
    __table_args__ = (
        CheckConstraint("trim(school_name) <> ''", name="school_name_nonempty"),
        CheckConstraint("trim(full_name) <> ''", name="full_name_nonempty"),
        CheckConstraint(
            "phone REGEXP '^[+]55[1-9][0-9][0-9]{8,9}$' AND RIGHT(phone, 1) BETWEEN '0' AND '9'",
            name="phone_format",
        ),
        CheckConstraint("trim(email) <> ''", name="email_nonempty"),
        CheckConstraint("trim(privacy_notice_version) <> ''", name="privacy_notice_nonempty"),
        CheckConstraint("status IN ('draft', 'submitted', 'completed')", name="status_valid"),
        CheckConstraint("access_token_hash REGEXP '^[0-9a-f]{64}$'", name="token_hash_format"),
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
        Index("ix_participations_started", "started_at", "id"),
        Index("ix_participations_school", "school_name", "started_at"),
        Index("ix_participations_status", "status", "started_at"),
        MYSQL_TABLE,
    )

    school_name: Mapped[str] = mapped_column(String(200))
    full_name: Mapped[str] = mapped_column(Text)
    phone: Mapped[str] = mapped_column(String(14))
    email: Mapped[str] = mapped_column(Text)
    privacy_notice_version: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(9), server_default=text("'draft'"))
    access_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    access_expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    started_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=text("(UTC_TIMESTAMP(6))")
    )
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class ParticipationSelection(Base):
    __tablename__ = "participation_selections"
    __table_args__ = MYSQL_TABLE

    participation_id: Mapped[UUID] = mapped_column(
        ForeignKey("participations.id", ondelete="CASCADE"), primary_key=True
    )
    statement_id: Mapped[UUID] = mapped_column(ForeignKey("statements.id"), primary_key=True)


class ParticipationAreaResult(Base):
    __tablename__ = "participation_area_results"
    __table_args__ = (
        CheckConstraint("is_winner IN (0, 1)", name="is_winner_boolean"),
        CheckConstraint("score BETWEEN 0 AND 25", name="score_range"),
        CheckConstraint("NOT is_winner OR score > 0", name="winner_positive"),
        Index("ix_area_winners", "area_id", "is_winner", "participation_id"),
        MYSQL_TABLE,
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
        CheckConstraint("is_recommended IN (0, 1)", name="is_recommended_boolean"),
        CheckConstraint("score >= 0", name="score_nonnegative"),
        CheckConstraint("NOT is_recommended OR score > 0", name="recommended_positive"),
        Index(
            "ix_course_recommendations",
            "course_id",
            "is_recommended",
            "participation_id",
        ),
        MYSQL_TABLE,
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
        CheckConstraint("agrees_with_result IN (0, 1)", name="agrees_with_result_boolean"),
        ForeignKeyConstraint(
            ["participation_id", "chosen_course_id"],
            [
                "participation_course_results.participation_id",
                "participation_course_results.course_id",
            ],
            name="fk_feedback_recommended_result",
            ondelete="CASCADE",
        ),
        CheckConstraint("trim(destination) <> ''", name="destination_nonempty"),
        CheckConstraint("trim(destination_instructions) <> ''", name="instructions_nonempty"),
        MYSQL_TABLE,
    )

    participation_id: Mapped[UUID] = mapped_column(
        ForeignKey("participations.id", ondelete="CASCADE"), primary_key=True
    )
    agrees_with_result: Mapped[bool]
    chosen_course_id: Mapped[UUID | None]
    destination: Mapped[str] = mapped_column(Text)
    destination_instructions: Mapped[str] = mapped_column(Text)
    answered_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=text("(UTC_TIMESTAMP(6))")
    )


class AdminAuditLog(CreatedAt, Base):
    __tablename__ = "admin_audit_logs"
    __table_args__ = (
        CheckConstraint("trim(action) <> ''", name="action_nonempty"),
        Index("ix_admin_audit_logs_created", "created_at"),
        MYSQL_TABLE,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    admin_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(Text)
    # Audit records survive controlled deletion of a participation.
    target_participation_id: Mapped[UUID | None]
