-- Fixed quiz schema, frozen for migration 0003.

CREATE TABLE areas (
	name TEXT NOT NULL,
	destination TEXT NOT NULL,
	destination_instructions TEXT NOT NULL,
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	CONSTRAINT pk_areas PRIMARY KEY (id),
	CONSTRAINT uq_areas_name UNIQUE (name),
	CONSTRAINT ck_areas_name_nonempty CHECK (btrim(name) <> ''),
	CONSTRAINT ck_areas_destination_nonempty CHECK (btrim(destination) <> ''),
	CONSTRAINT ck_areas_instructions_nonempty CHECK (btrim(destination_instructions) <> '')
);


CREATE TABLE participations (
	school_name TEXT NOT NULL,
	full_name TEXT NOT NULL,
	phone VARCHAR(14) NOT NULL,
	email TEXT NOT NULL,
	privacy_notice_version TEXT NOT NULL,
	status TEXT DEFAULT 'draft' NOT NULL,
	access_token_hash TEXT,
	access_expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	started_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	submitted_at TIMESTAMP WITH TIME ZONE,
	completed_at TIMESTAMP WITH TIME ZONE,
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	CONSTRAINT pk_participations PRIMARY KEY (id),
	CONSTRAINT ck_participations_school_name_nonempty CHECK (btrim(school_name) <> ''),
	CONSTRAINT ck_participations_full_name_nonempty CHECK (btrim(full_name) <> ''),
	CONSTRAINT ck_participations_phone_format CHECK (phone ~ '^\+55[1-9][0-9][0-9]{8,9}$'),
	CONSTRAINT ck_participations_email_nonempty CHECK (btrim(email) <> ''),
	CONSTRAINT ck_participations_privacy_notice_nonempty CHECK (btrim(privacy_notice_version) <> ''),
	CONSTRAINT ck_participations_status_valid CHECK (status IN ('draft', 'submitted', 'completed')),
	CONSTRAINT ck_participations_token_hash_format CHECK (access_token_hash ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_participations_submission_timestamp_matches_status CHECK ((status = 'draft' AND submitted_at IS NULL) OR (status IN ('submitted', 'completed') AND submitted_at IS NOT NULL)),
	CONSTRAINT ck_participations_completion_timestamp_matches_status CHECK ((status = 'completed') = (completed_at IS NOT NULL)),
	CONSTRAINT ck_participations_expiry_after_start CHECK (access_expires_at > started_at),
	CONSTRAINT ck_participations_submission_after_start CHECK (submitted_at IS NULL OR submitted_at >= started_at),
	CONSTRAINT ck_participations_completion_after_submission CHECK (completed_at IS NULL OR completed_at >= submitted_at),
	CONSTRAINT uq_participations_access_token_hash UNIQUE (access_token_hash)
);

CREATE INDEX ix_participations_school ON participations (school_name, started_at DESC);
CREATE INDEX ix_participations_started ON participations (started_at DESC, id);
CREATE INDEX ix_participations_status ON participations (status, started_at DESC);

CREATE TABLE statements (
	source_number SMALLINT NOT NULL,
	display_order SMALLINT NOT NULL,
	text TEXT NOT NULL,
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	CONSTRAINT pk_statements PRIMARY KEY (id),
	CONSTRAINT uq_statements_source_number UNIQUE (source_number),
	CONSTRAINT uq_statements_display_order UNIQUE (display_order),
	CONSTRAINT ck_statements_source_number_positive CHECK (source_number > 0),
	CONSTRAINT ck_statements_display_order_positive CHECK (display_order > 0),
	CONSTRAINT ck_statements_text_nonempty CHECK (btrim(text) <> '')
);


CREATE TABLE courses (
	area_id UUID NOT NULL,
	name TEXT NOT NULL,
	description TEXT,
	destination TEXT,
	destination_instructions TEXT,
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	CONSTRAINT pk_courses PRIMARY KEY (id),
	CONSTRAINT uq_courses_name UNIQUE (name),
	CONSTRAINT ck_courses_name_nonempty CHECK (btrim(name) <> ''),
	CONSTRAINT ck_courses_destination_pair CHECK ((destination IS NULL AND destination_instructions IS NULL) OR (destination IS NOT NULL AND btrim(destination) <> '' AND destination_instructions IS NOT NULL AND btrim(destination_instructions) <> '')),
	CONSTRAINT fk_courses_area_id_areas FOREIGN KEY(area_id) REFERENCES areas (id)
);

CREATE INDEX ix_courses_area ON courses (area_id);

CREATE TABLE participation_area_results (
	participation_id UUID NOT NULL,
	area_id UUID NOT NULL,
	score SMALLINT NOT NULL,
	is_winner BOOLEAN NOT NULL,
	CONSTRAINT pk_participation_area_results PRIMARY KEY (participation_id, area_id),
	CONSTRAINT ck_participation_area_results_score_range CHECK (score BETWEEN 0 AND 25),
	CONSTRAINT ck_participation_area_results_winner_positive CHECK (NOT is_winner OR score > 0),
	CONSTRAINT fk_participation_area_results_participation_id_participations FOREIGN KEY(participation_id) REFERENCES participations (id) ON DELETE CASCADE,
	CONSTRAINT fk_participation_area_results_area_id_areas FOREIGN KEY(area_id) REFERENCES areas (id)
);

CREATE INDEX ix_area_winners ON participation_area_results (area_id, participation_id) WHERE is_winner;

CREATE TABLE participation_selections (
	participation_id UUID NOT NULL,
	statement_id UUID NOT NULL,
	CONSTRAINT pk_participation_selections PRIMARY KEY (participation_id, statement_id),
	CONSTRAINT fk_participation_selections_participation_id_participations FOREIGN KEY(participation_id) REFERENCES participations (id) ON DELETE CASCADE,
	CONSTRAINT fk_participation_selections_statement_id_statements FOREIGN KEY(statement_id) REFERENCES statements (id)
);


CREATE TABLE participation_course_results (
	participation_id UUID NOT NULL,
	course_id UUID NOT NULL,
	score INTEGER NOT NULL,
	is_recommended BOOLEAN NOT NULL,
	CONSTRAINT pk_participation_course_results PRIMARY KEY (participation_id, course_id),
	CONSTRAINT ck_participation_course_results_score_nonnegative CHECK (score >= 0),
	CONSTRAINT ck_participation_course_results_recommended_positive CHECK (NOT is_recommended OR score > 0),
	CONSTRAINT fk_participation_course_results_participation_id_participations FOREIGN KEY(participation_id) REFERENCES participations (id) ON DELETE CASCADE,
	CONSTRAINT fk_participation_course_results_course_id_courses FOREIGN KEY(course_id) REFERENCES courses (id)
);

CREATE INDEX ix_course_recommendations ON participation_course_results (course_id, participation_id) WHERE is_recommended;

CREATE TABLE statement_course_weights (
	statement_id UUID NOT NULL,
	course_id UUID NOT NULL,
	weight SMALLINT DEFAULT 1 NOT NULL,
	CONSTRAINT pk_statement_course_weights PRIMARY KEY (statement_id, course_id),
	CONSTRAINT ck_statement_course_weights_weight_positive CHECK (weight > 0),
	CONSTRAINT fk_statement_course_weights_statement_id_statements FOREIGN KEY(statement_id) REFERENCES statements (id),
	CONSTRAINT fk_statement_course_weights_course_id_courses FOREIGN KEY(course_id) REFERENCES courses (id)
);

CREATE INDEX ix_weights_course ON statement_course_weights (course_id);

CREATE TABLE participation_feedback (
	participation_id UUID NOT NULL,
	agrees_with_result BOOLEAN NOT NULL,
	chosen_course_id UUID,
	destination TEXT NOT NULL,
	destination_instructions TEXT NOT NULL,
	answered_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_participation_feedback PRIMARY KEY (participation_id),
	CONSTRAINT fk_participation_feedback_participation_id_participatio_8314 FOREIGN KEY(participation_id, chosen_course_id) REFERENCES participation_course_results (participation_id, course_id),
	CONSTRAINT ck_participation_feedback_destination_nonempty CHECK (btrim(destination) <> ''),
	CONSTRAINT ck_participation_feedback_instructions_nonempty CHECK (btrim(destination_instructions) <> ''),
	CONSTRAINT ck_participation_feedback_agreement_matches_course CHECK ((agrees_with_result AND chosen_course_id IS NOT NULL) OR (NOT agrees_with_result AND chosen_course_id IS NULL)),
	CONSTRAINT fk_participation_feedback_participation_id_participations FOREIGN KEY(participation_id) REFERENCES participations (id) ON DELETE CASCADE
);


-- Selecao e resultados so podem mudar no rascunho. Todos bloqueiam o mesmo pai.
-- Inserir selecoes e resultados antes da transicao para submitted, na mesma transacao.
CREATE FUNCTION guard_participation_children() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_id uuid; v_status text;
BEGIN
    IF TG_OP = 'DELETE' THEN v_id := OLD.participation_id;
    ELSE v_id := NEW.participation_id; END IF;
    IF TG_OP = 'UPDATE' AND NEW.participation_id <> OLD.participation_id THEN
        RAISE EXCEPTION 'Participation cannot change';
    END IF;
    SELECT status INTO v_status FROM participations WHERE id = v_id FOR UPDATE;
    -- Permite cascata quando a participacao inteira e excluida pela rotina de retencao.
    IF NOT FOUND AND TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    IF v_status IS DISTINCT FROM 'draft' THEN
        RAISE EXCEPTION 'Submitted answers and results are immutable';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END;
$$;
CREATE TRIGGER guard_selections BEFORE INSERT OR UPDATE OR DELETE ON participation_selections
    FOR EACH ROW EXECUTE FUNCTION guard_participation_children();
CREATE TRIGGER guard_area_results BEFORE INSERT OR UPDATE OR DELETE ON participation_area_results
    FOR EACH ROW EXECUTE FUNCTION guard_participation_children();
CREATE TRIGGER guard_course_results BEFORE INSERT OR UPDATE OR DELETE ON participation_course_results
    FOR EACH ROW EXECUTE FUNCTION guard_participation_children();

CREATE FUNCTION guard_participation_state() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_count integer;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'draft' THEN
            RAISE EXCEPTION 'Start a draft participation';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.id <> OLD.id THEN
        RAISE EXCEPTION 'Participation identity cannot change';
    END IF;
    IF NEW.status <> OLD.status AND NOT (
        (OLD.status = 'draft' AND NEW.status = 'submitted')
        OR (OLD.status = 'submitted' AND NEW.status = 'completed')) THEN
        RAISE EXCEPTION 'Invalid participation state transition';
    END IF;
    IF OLD.status = 'draft' AND NEW.status = 'submitted' THEN
        SELECT count(*) INTO v_count FROM participation_selections WHERE participation_id = NEW.id;
        IF v_count <> 25 THEN
            RAISE EXCEPTION 'Submission requires exactly 25 unique selections; got %', v_count;
        END IF;
        IF (SELECT count(*) FROM participation_area_results WHERE participation_id = NEW.id)
            <> (SELECT count(*) FROM areas)
            OR (SELECT count(*) FROM participation_course_results WHERE participation_id = NEW.id)
            <> (SELECT count(*) FROM courses) THEN
            RAISE EXCEPTION 'Persist a result for every area and course before submitting';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM participation_area_results WHERE participation_id = NEW.id AND is_winner)
            OR NOT EXISTS (SELECT 1 FROM participation_course_results WHERE participation_id = NEW.id AND is_recommended) THEN
            RAISE EXCEPTION 'At least one winning area and recommended course are required';
        END IF;
    END IF;
    -- Submitted identity and timestamps are history; session revocation stays possible.
    IF OLD.status <> 'draft' THEN
        IF (to_jsonb(NEW) - ARRAY['status', 'completed_at', 'access_token_hash', 'access_expires_at'])
            IS DISTINCT FROM
            (to_jsonb(OLD) - ARRAY['status', 'completed_at', 'access_token_hash', 'access_expires_at'])
            OR (OLD.status = 'completed' AND NEW.completed_at IS DISTINCT FROM OLD.completed_at) THEN
            RAISE EXCEPTION 'Submitted participation details are immutable';
        END IF;
    END IF;
    IF NEW.status = 'completed' AND NOT EXISTS (
        SELECT 1 FROM participation_feedback WHERE participation_id = NEW.id) THEN
        RAISE EXCEPTION 'Completion requires feedback';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER guard_participations BEFORE INSERT OR UPDATE ON participations
    FOR EACH ROW EXECUTE FUNCTION guard_participation_state();

CREATE FUNCTION guard_feedback() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_status text;
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        PERFORM 1 FROM participations WHERE id = OLD.participation_id FOR UPDATE;
        IF NOT FOUND AND TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        RAISE EXCEPTION 'Feedback is immutable; delete the participation for controlled retention';
    END IF;
    SELECT status INTO v_status FROM participations WHERE id = NEW.participation_id FOR UPDATE;
    IF v_status IS DISTINCT FROM 'submitted' THEN
        RAISE EXCEPTION 'Feedback requires a submitted participation';
    END IF;
    IF NEW.agrees_with_result AND NOT EXISTS (
        SELECT 1 FROM participation_course_results WHERE participation_id = NEW.participation_id
            AND course_id = NEW.chosen_course_id AND is_recommended) THEN
        RAISE EXCEPTION 'Choose one of the recommended courses';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER guard_participation_feedback BEFORE INSERT OR UPDATE OR DELETE ON participation_feedback
    FOR EACH ROW EXECUTE FUNCTION guard_feedback();

