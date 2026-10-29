-- Frozen integrity rules for revision 0001. Do not edit after deployment.

-- Catalogo: bloquear versao pai antes de alterar filhos evita corrida com publicacao.
CREATE FUNCTION guard_catalog_draft() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_id uuid;
    v_status text;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF NEW.id IS DISTINCT FROM OLD.id THEN
            RAISE EXCEPTION 'Catalog identity cannot change';
        END IF;
    END IF;
    IF TG_OP = 'DELETE' THEN v_id := OLD.quiz_version_id;
    ELSE v_id := NEW.quiz_version_id; END IF;
    IF TG_OP = 'UPDATE' AND NEW.quiz_version_id <> OLD.quiz_version_id THEN
        RAISE EXCEPTION 'Catalog version cannot change';
    END IF;
    SELECT status INTO v_status FROM quiz_versions WHERE id = v_id FOR UPDATE;
    IF v_status IS DISTINCT FROM 'draft' THEN
        RAISE EXCEPTION 'Published catalog is immutable; create a new version';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END;
$$;

CREATE TRIGGER guard_areas BEFORE INSERT OR UPDATE OR DELETE ON areas
    FOR EACH ROW EXECUTE FUNCTION guard_catalog_draft();
CREATE TRIGGER guard_courses BEFORE INSERT OR UPDATE OR DELETE ON courses
    FOR EACH ROW EXECUTE FUNCTION guard_catalog_draft();
CREATE TRIGGER guard_statements BEFORE INSERT OR UPDATE OR DELETE ON statements
    FOR EACH ROW EXECUTE FUNCTION guard_catalog_draft();

-- A relacao N:N nao tem coluna id: usar guard separado.
CREATE FUNCTION guard_weights_draft() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_id uuid; v_status text;
BEGIN
    IF TG_OP = 'DELETE' THEN v_id := OLD.quiz_version_id;
    ELSE v_id := NEW.quiz_version_id; END IF;
    IF TG_OP = 'UPDATE' AND NEW.quiz_version_id <> OLD.quiz_version_id THEN
        RAISE EXCEPTION 'Weight version cannot change';
    END IF;
    SELECT status INTO v_status FROM quiz_versions WHERE id = v_id FOR UPDATE;
    IF v_status IS DISTINCT FROM 'draft' THEN
        RAISE EXCEPTION 'Published weights are immutable';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END;
$$;
CREATE TRIGGER guard_weights BEFORE INSERT OR UPDATE OR DELETE ON statement_course_weights
    FOR EACH ROW EXECUTE FUNCTION guard_weights_draft();

CREATE FUNCTION guard_quiz_version() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'draft' THEN RAISE EXCEPTION 'Create version as draft'; END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        IF OLD.status <> 'draft' THEN RAISE EXCEPTION 'Published version cannot be deleted'; END IF;
        RETURN OLD;
    END IF;
    IF NEW.id <> OLD.id THEN RAISE EXCEPTION 'Version identity cannot change'; END IF;
    IF OLD.status <> 'draft' THEN
        IF OLD.status = 'published' AND NEW.status = 'archived'
            AND (to_jsonb(NEW) - 'status') = (to_jsonb(OLD) - 'status') THEN
            RETURN NEW;
        END IF;
        RAISE EXCEPTION 'Published version is immutable except archival';
    END IF;
    IF NEW.status = 'archived' THEN RAISE EXCEPTION 'Publish before archival'; END IF;
    IF NEW.status = 'published' THEN
        IF (SELECT count(*) FROM statements WHERE quiz_version_id = NEW.id) < 25 THEN
            RAISE EXCEPTION 'Publication requires at least 25 statements';
        END IF;
        IF EXISTS (SELECT 1 FROM statements s WHERE s.quiz_version_id = NEW.id
            AND NOT EXISTS (SELECT 1 FROM statement_course_weights w WHERE w.statement_id = s.id)) THEN
            RAISE EXCEPTION 'Every statement needs at least one course';
        END IF;
        IF EXISTS (SELECT 1 FROM courses c WHERE c.quiz_version_id = NEW.id
            AND NOT EXISTS (SELECT 1 FROM statement_course_weights w WHERE w.course_id = c.id)) THEN
            RAISE EXCEPTION 'Every course needs a statement mapping';
        END IF;
        IF EXISTS (SELECT 1 FROM areas a WHERE a.quiz_version_id = NEW.id
            AND NOT EXISTS (SELECT 1 FROM courses c WHERE c.area_id = a.id)) THEN
            RAISE EXCEPTION 'Every area needs at least one course';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER guard_quiz_versions BEFORE INSERT OR UPDATE OR DELETE ON quiz_versions
    FOR EACH ROW EXECUTE FUNCTION guard_quiz_version();

-- Selecao e resultados so podem mudar no rascunho. Todos bloqueiam o mesmo pai.
-- Inserir selecoes e resultados antes da transicao para submitted, na mesma transacao.
CREATE FUNCTION guard_participation_children() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_id uuid; v_status text;
BEGIN
    IF TG_OP = 'DELETE' THEN v_id := OLD.participation_id;
    ELSE v_id := NEW.participation_id; END IF;
    IF TG_OP = 'UPDATE' AND (NEW.participation_id <> OLD.participation_id
        OR NEW.quiz_version_id <> OLD.quiz_version_id) THEN
        RAISE EXCEPTION 'Participation/version cannot change';
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
DECLARE v_status text; v_count integer;
BEGIN
    IF TG_OP = 'INSERT' THEN
        SELECT status INTO v_status FROM quiz_versions WHERE id = NEW.quiz_version_id FOR SHARE;
        IF NEW.status <> 'draft' OR v_status IS DISTINCT FROM 'published' THEN
            RAISE EXCEPTION 'Start a draft against a published version';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.id <> OLD.id OR NEW.quiz_version_id <> OLD.quiz_version_id THEN
        RAISE EXCEPTION 'Participation identity/version cannot change';
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
            <> (SELECT count(*) FROM areas WHERE quiz_version_id = NEW.quiz_version_id)
            OR (SELECT count(*) FROM participation_course_results WHERE participation_id = NEW.id)
            <> (SELECT count(*) FROM courses WHERE quiz_version_id = NEW.quiz_version_id) THEN
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

