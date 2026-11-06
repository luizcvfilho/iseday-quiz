"""Allow agreement without choosing a course, preserving existing feedback snapshots."""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def _guard_feedback(*, optional_course: bool):
    course_condition = "AND NEW.chosen_course_id IS NOT NULL" if optional_course else ""
    op.execute(f"""
        CREATE OR REPLACE FUNCTION guard_feedback() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE v_status text;
        BEGIN
            IF TG_OP IN ('UPDATE', 'DELETE') THEN
                PERFORM 1 FROM participations WHERE id = OLD.participation_id FOR UPDATE;
                IF NOT FOUND AND TG_OP = 'DELETE' THEN RETURN OLD; END IF;
                RAISE EXCEPTION
                    'Feedback is immutable; delete the participation for controlled retention';
            END IF;
            SELECT status INTO v_status FROM participations
                WHERE id = NEW.participation_id FOR UPDATE;
            IF v_status IS DISTINCT FROM 'submitted' THEN
                RAISE EXCEPTION 'Feedback requires a submitted participation';
            END IF;
            IF NEW.agrees_with_result {course_condition} AND NOT EXISTS (
                SELECT 1 FROM participation_course_results
                WHERE participation_id = NEW.participation_id
                    AND course_id = NEW.chosen_course_id AND is_recommended) THEN
                RAISE EXCEPTION 'Choose one of the recommended courses';
            END IF;
            RETURN NEW;
        END;
        $$;
    """)


def upgrade():
    op.drop_constraint(
        "ck_participation_feedback_agreement_matches_course", "participation_feedback"
    )
    op.create_check_constraint(
        "agreement_matches_course",
        "participation_feedback",
        "agrees_with_result OR chosen_course_id IS NULL",
    )
    _guard_feedback(optional_course=True)


def downgrade():
    # Restoring the required-course constraint must not discard completed answers.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM participation_feedback
                       WHERE agrees_with_result AND chosen_course_id IS NULL) THEN
                RAISE EXCEPTION 'Automatic referrals exist; restore a backup to downgrade';
            END IF;
        END $$;
    """)
    op.drop_constraint(
        "ck_participation_feedback_agreement_matches_course", "participation_feedback"
    )
    op.create_check_constraint(
        "agreement_matches_course",
        "participation_feedback",
        "(agrees_with_result AND chosen_course_id IS NOT NULL) OR "
        "(NOT agrees_with_result AND chosen_course_id IS NULL)",
    )
    _guard_feedback(optional_course=False)
