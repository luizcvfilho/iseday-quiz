-- ISE Day: proposta inicial de esquema PostgreSQL.
-- Nao aplicado a um servidor. Converter em migracoes Alembic na implementacao.
-- Catalogos sao versionados; dados pessoais pertencem a cada participacao.
-- A API calcula os resultados; as triggers preservam estados, contagem e historico.

BEGIN;

CREATE TABLE schools (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL CHECK (btrim(name) <> ''),
    city text,
    state_code varchar(2),
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_schools_name ON schools (lower(name));

CREATE TABLE admin_users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL CHECK (btrim(name) <> ''),
    email text NOT NULL CHECK (btrim(email) <> ''),
    password_hash text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_admin_users_email ON admin_users (lower(email));

CREATE TABLE admin_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_user_id uuid NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    token_hash text NOT NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    CHECK (expires_at > created_at)
);
CREATE INDEX ix_admin_sessions_user ON admin_sessions (admin_user_id);

CREATE TABLE quiz_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_name text NOT NULL CHECK (btrim(event_name) <> ''),
    version_number integer NOT NULL UNIQUE CHECK (version_number > 0),
    status text NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'published', 'archived')),
    required_selection_count smallint NOT NULL DEFAULT 25
        CHECK (required_selection_count = 25),
    scoring_method text NOT NULL DEFAULT 'area_distinct_count_course_sum_v1'
        CHECK (scoring_method = 'area_distinct_count_course_sum_v1'),
    psychology_destination text NOT NULL CHECK (btrim(psychology_destination) <> ''),
    psychology_instructions text NOT NULL CHECK (btrim(psychology_instructions) <> ''),
    created_at timestamptz NOT NULL DEFAULT now()
);
-- O MVP tem uma unica versao publicada ativa.
CREATE UNIQUE INDEX uq_single_published_quiz
    ON quiz_versions ((status)) WHERE status = 'published';

CREATE TABLE areas (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    quiz_version_id uuid NOT NULL REFERENCES quiz_versions(id),
    name text NOT NULL CHECK (btrim(name) <> ''),
    destination text NOT NULL CHECK (btrim(destination) <> ''),
    destination_instructions text NOT NULL CHECK (btrim(destination_instructions) <> ''),
    UNIQUE (id, quiz_version_id),
    UNIQUE (quiz_version_id, name)
);

CREATE TABLE courses (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    quiz_version_id uuid NOT NULL REFERENCES quiz_versions(id),
    area_id uuid NOT NULL,
    name text NOT NULL CHECK (btrim(name) <> ''),
    description text,
    -- Nulos significam usar o destino da area, apos validacao institucional.
    destination text,
    destination_instructions text,
    UNIQUE (id, quiz_version_id),
    UNIQUE (quiz_version_id, name),
    FOREIGN KEY (area_id, quiz_version_id) REFERENCES areas(id, quiz_version_id)
);
CREATE INDEX ix_courses_area ON courses (area_id, quiz_version_id);

CREATE TABLE statements (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    quiz_version_id uuid NOT NULL REFERENCES quiz_versions(id),
    source_number smallint NOT NULL CHECK (source_number > 0),
    display_order smallint NOT NULL CHECK (display_order > 0),
    text text NOT NULL CHECK (btrim(text) <> ''),
    UNIQUE (id, quiz_version_id),
    UNIQUE (quiz_version_id, source_number),
    UNIQUE (quiz_version_id, display_order)
);

CREATE TABLE statement_course_weights (
    quiz_version_id uuid NOT NULL REFERENCES quiz_versions(id),
    statement_id uuid NOT NULL,
    course_id uuid NOT NULL,
    weight smallint NOT NULL DEFAULT 1 CHECK (weight > 0),
    PRIMARY KEY (statement_id, course_id),
    FOREIGN KEY (statement_id, quiz_version_id) REFERENCES statements(id, quiz_version_id),
    FOREIGN KEY (course_id, quiz_version_id) REFERENCES courses(id, quiz_version_id)
);
CREATE INDEX ix_weights_course ON statement_course_weights (course_id, quiz_version_id);

CREATE TABLE participations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    quiz_version_id uuid NOT NULL REFERENCES quiz_versions(id),
    school_id uuid NOT NULL REFERENCES schools(id),
    full_name text NOT NULL CHECK (btrim(full_name) <> ''),
    -- API normaliza +55, DDD e numero; SQL guarda texto, nunca inteiro.
    phone varchar(14) NOT NULL CHECK (phone ~ '^\+55[1-9][0-9][0-9]{8,9}$'),
    email text NOT NULL CHECK (btrim(email) <> ''),
    privacy_notice_version text NOT NULL CHECK (btrim(privacy_notice_version) <> ''),
    status text NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'submitted', 'completed')),
    access_token_hash text UNIQUE CHECK (access_token_hash ~ '^[0-9a-f]{64}$'),
    access_expires_at timestamptz NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    submitted_at timestamptz,
    completed_at timestamptz,
    UNIQUE (id, quiz_version_id),
    CHECK ((status = 'draft' AND submitted_at IS NULL)
        OR (status IN ('submitted', 'completed') AND submitted_at IS NOT NULL)),
    CHECK ((status = 'completed') = (completed_at IS NOT NULL)),
    CHECK (access_expires_at > started_at),
    CHECK (submitted_at IS NULL OR submitted_at >= started_at),
    CHECK (completed_at IS NULL OR completed_at >= submitted_at)
);
-- Contatos nao sao UNIQUE: pessoas diferentes podem compartilhar telefone/email.
CREATE INDEX ix_participations_started ON participations (started_at DESC, id);
CREATE INDEX ix_participations_school ON participations (school_id, started_at DESC);
CREATE INDEX ix_participations_status ON participations (status, started_at DESC);
CREATE INDEX ix_participations_version ON participations (quiz_version_id);

CREATE TABLE participation_selections (
    participation_id uuid NOT NULL,
    quiz_version_id uuid NOT NULL,
    statement_id uuid NOT NULL,
    PRIMARY KEY (participation_id, statement_id),
    FOREIGN KEY (participation_id, quiz_version_id)
        REFERENCES participations(id, quiz_version_id) ON DELETE CASCADE,
    FOREIGN KEY (statement_id, quiz_version_id) REFERENCES statements(id, quiz_version_id)
);

CREATE TABLE participation_area_results (
    participation_id uuid NOT NULL,
    quiz_version_id uuid NOT NULL,
    area_id uuid NOT NULL,
    score smallint NOT NULL CHECK (score BETWEEN 0 AND 25),
    is_winner boolean NOT NULL,
    PRIMARY KEY (participation_id, area_id),
    FOREIGN KEY (participation_id, quiz_version_id)
        REFERENCES participations(id, quiz_version_id) ON DELETE CASCADE,
    FOREIGN KEY (area_id, quiz_version_id) REFERENCES areas(id, quiz_version_id),
    CHECK (NOT is_winner OR score > 0)
);
CREATE INDEX ix_area_winners ON participation_area_results (area_id, participation_id)
    WHERE is_winner;

CREATE TABLE participation_course_results (
    participation_id uuid NOT NULL,
    quiz_version_id uuid NOT NULL,
    course_id uuid NOT NULL,
    score integer NOT NULL CHECK (score >= 0),
    is_recommended boolean NOT NULL,
    PRIMARY KEY (participation_id, course_id),
    FOREIGN KEY (participation_id, quiz_version_id)
        REFERENCES participations(id, quiz_version_id) ON DELETE CASCADE,
    FOREIGN KEY (course_id, quiz_version_id) REFERENCES courses(id, quiz_version_id),
    CHECK (NOT is_recommended OR score > 0)
);
CREATE INDEX ix_course_recommendations
    ON participation_course_results (course_id, participation_id) WHERE is_recommended;

CREATE TABLE participation_feedback (
    participation_id uuid PRIMARY KEY REFERENCES participations(id) ON DELETE CASCADE,
    agrees_with_result boolean NOT NULL,
    chosen_course_id uuid,
    -- Snapshot do encaminhamento efetivamente exibido ao aluno.
    destination text NOT NULL CHECK (btrim(destination) <> ''),
    destination_instructions text NOT NULL CHECK (btrim(destination_instructions) <> ''),
    answered_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (participation_id, chosen_course_id)
        REFERENCES participation_course_results(participation_id, course_id),
    CHECK ((agrees_with_result AND chosen_course_id IS NOT NULL)
        OR (NOT agrees_with_result AND chosen_course_id IS NULL))
);

CREATE TABLE admin_audit_logs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    admin_user_id uuid REFERENCES admin_users(id) ON DELETE SET NULL,
    action text NOT NULL CHECK (btrim(action) <> ''),
    -- Sem FK: auditoria pode sobreviver a exclusao controlada da participacao.
    target_participation_id uuid,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_admin_audit_logs_created ON admin_audit_logs (created_at DESC);

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

-- A API usa usuario sem DDL. Permissoes/roles, politicas de retencao e migracoes
-- serao configuradas na implementacao. Nao expor estas tabelas diretamente ao browser.
COMMIT;
