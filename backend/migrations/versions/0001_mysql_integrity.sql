-- Frozen integrity rules for revision 0001_mysql.
-- Cascades bypass row triggers in InnoDB, allowing retention by deleting the parent.

CREATE TRIGGER guard_participation_selections_insert
BEFORE INSERT ON participation_selections
FOR EACH ROW
BEGIN
    DECLARE v_status VARCHAR(9);
    SELECT status INTO v_status FROM participations WHERE id = NEW.participation_id FOR UPDATE;
    IF NOT (v_status <=> 'draft') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Submitted answers and results are immutable';
    END IF;
END
$$

CREATE TRIGGER guard_participation_selections_update
BEFORE UPDATE ON participation_selections
FOR EACH ROW
BEGIN
    DECLARE v_status VARCHAR(9);
    IF NOT (NEW.participation_id <=> OLD.participation_id) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Participation cannot change';
    END IF;
    SELECT status INTO v_status FROM participations WHERE id = NEW.participation_id FOR UPDATE;
    IF NOT (v_status <=> 'draft') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Submitted answers and results are immutable';
    END IF;
END
$$

CREATE TRIGGER guard_participation_selections_delete
BEFORE DELETE ON participation_selections
FOR EACH ROW
BEGIN
    DECLARE v_status VARCHAR(9);
    SELECT status INTO v_status FROM participations WHERE id = OLD.participation_id FOR UPDATE;
    IF NOT (v_status <=> 'draft') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Submitted answers and results are immutable';
    END IF;
END
$$

CREATE TRIGGER guard_participation_area_results_insert
BEFORE INSERT ON participation_area_results
FOR EACH ROW
BEGIN
    DECLARE v_status VARCHAR(9);
    SELECT status INTO v_status FROM participations WHERE id = NEW.participation_id FOR UPDATE;
    IF NOT (v_status <=> 'draft') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Submitted answers and results are immutable';
    END IF;
END
$$

CREATE TRIGGER guard_participation_area_results_update
BEFORE UPDATE ON participation_area_results
FOR EACH ROW
BEGIN
    DECLARE v_status VARCHAR(9);
    IF NOT (NEW.participation_id <=> OLD.participation_id) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Participation cannot change';
    END IF;
    SELECT status INTO v_status FROM participations WHERE id = NEW.participation_id FOR UPDATE;
    IF NOT (v_status <=> 'draft') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Submitted answers and results are immutable';
    END IF;
END
$$

CREATE TRIGGER guard_participation_area_results_delete
BEFORE DELETE ON participation_area_results
FOR EACH ROW
BEGIN
    DECLARE v_status VARCHAR(9);
    SELECT status INTO v_status FROM participations WHERE id = OLD.participation_id FOR UPDATE;
    IF NOT (v_status <=> 'draft') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Submitted answers and results are immutable';
    END IF;
END
$$

CREATE TRIGGER guard_participation_course_results_insert
BEFORE INSERT ON participation_course_results
FOR EACH ROW
BEGIN
    DECLARE v_status VARCHAR(9);
    SELECT status INTO v_status FROM participations WHERE id = NEW.participation_id FOR UPDATE;
    IF NOT (v_status <=> 'draft') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Submitted answers and results are immutable';
    END IF;
END
$$

CREATE TRIGGER guard_participation_course_results_update
BEFORE UPDATE ON participation_course_results
FOR EACH ROW
BEGIN
    DECLARE v_status VARCHAR(9);
    IF NOT (NEW.participation_id <=> OLD.participation_id) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Participation cannot change';
    END IF;
    SELECT status INTO v_status FROM participations WHERE id = NEW.participation_id FOR UPDATE;
    IF NOT (v_status <=> 'draft') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Submitted answers and results are immutable';
    END IF;
END
$$

CREATE TRIGGER guard_participation_course_results_delete
BEFORE DELETE ON participation_course_results
FOR EACH ROW
BEGIN
    DECLARE v_status VARCHAR(9);
    SELECT status INTO v_status FROM participations WHERE id = OLD.participation_id FOR UPDATE;
    IF NOT (v_status <=> 'draft') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Submitted answers and results are immutable';
    END IF;
END
$$

CREATE TRIGGER guard_participations_insert
BEFORE INSERT ON participations
FOR EACH ROW
BEGIN
    IF NEW.status <> 'draft' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Start a draft participation';
    END IF;
END
$$

CREATE TRIGGER guard_participations_update
BEFORE UPDATE ON participations
FOR EACH ROW
BEGIN
    DECLARE selection_count INT;
    DECLARE area_count INT;
    DECLARE course_count INT;
    DECLARE winner_count INT;
    DECLARE recommendation_count INT;
    DECLARE feedback_count INT;
    DECLARE failure_message VARCHAR(128);
    IF NOT (NEW.id <=> OLD.id) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Participation identity cannot change';
    END IF;
    IF NEW.status <> OLD.status AND NOT (
        (OLD.status = 'draft' AND NEW.status = 'submitted')
        OR (OLD.status = 'submitted' AND NEW.status = 'completed')
    ) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid participation state transition';
    END IF;
    IF OLD.status = 'draft' AND NEW.status = 'submitted' THEN
        -- Read current rows after locking the parent, even under REPEATABLE READ.
        SELECT COUNT(*) INTO selection_count FROM participation_selections
            WHERE participation_id = NEW.id FOR SHARE;
        IF selection_count <> 25 THEN
            SET failure_message = CONCAT(
                'Submission requires exactly 25 unique selections; got ', selection_count
            );
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = failure_message;
        END IF;
        SELECT COUNT(*), COALESCE(SUM(is_winner), 0) INTO area_count, winner_count
            FROM participation_area_results WHERE participation_id = NEW.id FOR SHARE;
        SELECT COUNT(*), COALESCE(SUM(is_recommended), 0) INTO course_count, recommendation_count
            FROM participation_course_results WHERE participation_id = NEW.id FOR SHARE;
        IF area_count <> (SELECT COUNT(*) FROM areas)
            OR course_count <> (SELECT COUNT(*) FROM courses) THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'Persist a result for every area and course before submitting';
        END IF;
        IF winner_count = 0 OR recommendation_count = 0 THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'At least one winning area and recommended course are required';
        END IF;
    END IF;
    IF OLD.status <> 'draft' AND (
        NOT (NEW.school_name <=> OLD.school_name)
        OR NOT (NEW.full_name <=> OLD.full_name)
        OR NOT (NEW.phone <=> OLD.phone)
        OR NOT (NEW.email <=> OLD.email)
        OR NOT (NEW.privacy_notice_version <=> OLD.privacy_notice_version)
        OR NOT (NEW.started_at <=> OLD.started_at)
        OR NOT (NEW.submitted_at <=> OLD.submitted_at)
        OR (OLD.status = 'completed' AND NOT (NEW.completed_at <=> OLD.completed_at))
    ) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Submitted participation details are immutable';
    END IF;
    IF NEW.status = 'completed' THEN
        SELECT COUNT(*) INTO feedback_count FROM participation_feedback
            WHERE participation_id = NEW.id FOR SHARE;
        IF feedback_count = 0 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Completion requires feedback';
        END IF;
    END IF;
END
$$

CREATE TRIGGER guard_feedback_insert
BEFORE INSERT ON participation_feedback
FOR EACH ROW
BEGIN
    DECLARE v_status VARCHAR(9);
    DECLARE recommendation_count INT;
    SELECT status INTO v_status FROM participations WHERE id = NEW.participation_id FOR UPDATE;
    IF NOT (v_status <=> 'submitted') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Feedback requires a submitted participation';
    END IF;
    IF NEW.chosen_course_id IS NOT NULL THEN
        IF NOT NEW.agrees_with_result THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Only agreement may specify a course';
        END IF;
        SELECT COUNT(*) INTO recommendation_count FROM participation_course_results
            WHERE participation_id = NEW.participation_id
            AND course_id = NEW.chosen_course_id AND is_recommended FOR SHARE;
        IF recommendation_count = 0 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Choose one of the recommended courses';
        END IF;
    END IF;
END
$$

CREATE TRIGGER guard_feedback_update
BEFORE UPDATE ON participation_feedback
FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Feedback is immutable'
$$

CREATE TRIGGER guard_feedback_delete
BEFORE DELETE ON participation_feedback
FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete the participation for controlled retention'
$$

CREATE TRIGGER guard_catalog_areas_insert
BEFORE INSERT ON areas
FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'The quiz catalog is fixed and cannot be changed'
$$

CREATE TRIGGER guard_catalog_areas_update
BEFORE UPDATE ON areas
FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'The quiz catalog is fixed and cannot be changed'
$$

CREATE TRIGGER guard_catalog_areas_delete
BEFORE DELETE ON areas
FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'The quiz catalog is fixed and cannot be changed'
$$

CREATE TRIGGER guard_catalog_courses_insert
BEFORE INSERT ON courses
FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'The quiz catalog is fixed and cannot be changed'
$$

CREATE TRIGGER guard_catalog_courses_update
BEFORE UPDATE ON courses
FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'The quiz catalog is fixed and cannot be changed'
$$

CREATE TRIGGER guard_catalog_courses_delete
BEFORE DELETE ON courses
FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'The quiz catalog is fixed and cannot be changed'
$$

CREATE TRIGGER guard_catalog_statements_insert
BEFORE INSERT ON statements
FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'The quiz catalog is fixed and cannot be changed'
$$

CREATE TRIGGER guard_catalog_statements_update
BEFORE UPDATE ON statements
FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'The quiz catalog is fixed and cannot be changed'
$$

CREATE TRIGGER guard_catalog_statements_delete
BEFORE DELETE ON statements
FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'The quiz catalog is fixed and cannot be changed'
$$

CREATE TRIGGER guard_catalog_statement_course_weights_insert
BEFORE INSERT ON statement_course_weights
FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'The quiz catalog is fixed and cannot be changed'
$$

CREATE TRIGGER guard_catalog_statement_course_weights_update
BEFORE UPDATE ON statement_course_weights
FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'The quiz catalog is fixed and cannot be changed'
$$

CREATE TRIGGER guard_catalog_statement_course_weights_delete
BEFORE DELETE ON statement_course_weights
FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'The quiz catalog is fixed and cannot be changed'
$$
