"""Allow participants to revise their confirmation and referral."""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _guard_feedback(*, allow_updates: bool):
    update_guard = (
        """
        IF NEW.participation_id IS DISTINCT FROM OLD.participation_id THEN
            RAISE EXCEPTION 'Feedback participation cannot change';
        END IF;
        IF v_status IS DISTINCT FROM 'completed' THEN
            RAISE EXCEPTION 'Feedback revisions require a completed participation';
        END IF;
        """
        if allow_updates
        else "RAISE EXCEPTION 'Feedback is immutable';"
    )
    op.execute(f"""
        CREATE OR REPLACE FUNCTION guard_feedback() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE v_status text;
        BEGIN
            IF TG_OP IN ('UPDATE', 'DELETE') THEN
                SELECT status INTO v_status FROM participations
                    WHERE id = OLD.participation_id FOR UPDATE;
                IF TG_OP = 'DELETE' THEN
                    IF NOT FOUND THEN RETURN OLD; END IF;
                    RAISE EXCEPTION
                        'Delete the participation for controlled retention';
                END IF;
                {update_guard}
            ELSE
                SELECT status INTO v_status FROM participations
                    WHERE id = NEW.participation_id FOR UPDATE;
                IF v_status IS DISTINCT FROM 'submitted' THEN
                    RAISE EXCEPTION 'Feedback requires a submitted participation';
                END IF;
            END IF;
            IF NEW.agrees_with_result AND NEW.chosen_course_id IS NOT NULL AND NOT EXISTS (
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
    _guard_feedback(allow_updates=True)


def downgrade():
    _guard_feedback(allow_updates=False)
