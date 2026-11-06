-- Frozen integrity rules for revision 0001. Do not edit after deployment.

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
        SELECT status INTO v_status FROM participations
            WHERE id = OLD.participation_id FOR UPDATE;
        IF TG_OP = 'DELETE' THEN
            IF NOT FOUND THEN RETURN OLD; END IF;
            RAISE EXCEPTION
                'Delete the participation for controlled retention';
        END IF;
        IF NEW.participation_id IS DISTINCT FROM OLD.participation_id THEN
            RAISE EXCEPTION 'Feedback participation cannot change';
        END IF;
        IF v_status IS DISTINCT FROM 'completed' THEN
            RAISE EXCEPTION 'Feedback revisions require a completed participation';
        END IF;
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
CREATE TRIGGER guard_participation_feedback BEFORE INSERT OR UPDATE OR DELETE ON participation_feedback
    FOR EACH ROW EXECUTE FUNCTION guard_feedback();
