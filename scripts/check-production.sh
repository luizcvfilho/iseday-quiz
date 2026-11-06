#!/usr/bin/env bash
# Ensaio com imagens de produção, HTTPS e banco/volumes exclusivamente descartáveis.
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
npm --prefix frontend run browser:check
test_dir="$(mktemp -d)"
project="iseday-production-test-$(date +%s)-$$"
compose=(docker compose --project-name "$project" --env-file "$test_dir/production.env" -f compose.production.yaml)
cleanup() {
  status=$?
  trap - EXIT
  if [[ "$status" != 0 ]]; then
    "${compose[@]}" logs --tail 80 || true
  fi
  "${compose[@]}" down --volumes --remove-orphans || true
  docker image rm "iseday-quiz-production-api:$project" "iseday-quiz-production-frontend:$project" >/dev/null 2>&1 || true
  rm -rf "$test_dir"
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Elimina interferência das variáveis exportadas de outros ambientes.
unset DATABASE_URL POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD SITE_ADDRESS
unset HTTP_BIND_ADDRESS HTTP_PORT HTTPS_PORT APP_IMAGE_TAG
unset PRIVACY_NOTICE_VERSION PRIVACY_NOTICE_TEXT
unset PARTICIPANT_SESSION_MINUTES PARTICIPANT_REGISTRATION_LIMIT PARTICIPANT_SUBMISSION_LIMIT
unset ADMIN_SESSION_MINUTES ADMIN_LOGIN_LIMIT
umask 077
password="$(openssl rand -hex 32)"
cat > "$test_dir/production.env" <<EOF
SITE_ADDRESS=localhost
HTTP_BIND_ADDRESS=127.0.0.1
HTTP_PORT=0
HTTPS_PORT=0
APP_IMAGE_TAG=$project
POSTGRES_DB=iseday_production_test
POSTGRES_USER=iseday
POSTGRES_PASSWORD=$password
DATABASE_URL=postgresql+psycopg://iseday:$password@db:5432/iseday_production_test
PRIVACY_NOTICE_VERSION=test-v1
PRIVACY_NOTICE_TEXT=Ensaio de produção. Use apenas dados fictícios.
EOF
unset password
"${compose[@]}" config --quiet
"${compose[@]}" up --build --detach --wait --wait-timeout 120

# Os dados fictícios só são criados no banco *_test do projeto temporário.
"${compose[@]}" exec -T api /app/.venv/bin/python - <<'PY'
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.admin.__main__ import save_account
from app.core.config import get_settings
from app.db import build_engine

settings = get_settings()
assert make_url(str(settings.database_url)).database == "iseday_production_test"
engine = build_engine(settings)
try:
    with Session(engine) as session, session.begin():
        save_account(
            session, "create", "admin@example.org", "admin test password only", "Equipe de teste"
        )
finally:
    engine.dispose()
PY

https_address="$("${compose[@]}" port frontend 443)"
export ISEDAY_PRODUCTION_TEST_URL="https://localhost:${https_address##*:}"
npm --prefix frontend test -- --workers=1

# Reiniciar os containers não pode apagar a participação nem o catálogo fixo.
"${compose[@]}" restart db api frontend
"${compose[@]}" up --detach --wait --wait-timeout 120
"${compose[@]}" exec -T api /app/.venv/bin/python - <<'PY'
from sqlalchemy import func, select
from app.core.config import get_settings
from app.db import build_engine
from app.models import Participation, Statement, Course

engine = build_engine(get_settings())
try:
    with engine.connect() as connection:
        assert connection.scalar(
            select(func.count()).select_from(Participation).where(Participation.status == "completed")
        ) == 1
        assert connection.scalar(select(func.count()).select_from(Statement)) == 74
        assert connection.scalar(select(func.count()).select_from(Course)) == 9
finally:
    engine.dispose()
PY

# Exercita o procedimento documentado de backup e restauração em uma base nova.
"${compose[@]}" exec -T db sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' > "$test_dir/quiz.dump"
"${compose[@]}" exec -T db sh -c 'exec createdb -U "$POSTGRES_USER" iseday_restore_check'
"${compose[@]}" exec -T db sh -c 'exec pg_restore -U "$POSTGRES_USER" -d iseday_restore_check --exit-on-error --single-transaction' < "$test_dir/quiz.dump"
restored_count="$("${compose[@]}" exec -T db sh -c 'exec psql -U "$POSTGRES_USER" -d iseday_restore_check -Atc "SELECT count(*) FROM participations"')"
[[ "$restored_count" == 1 ]]
printf '%s\n' 'Ensaio de produção aprovado: HTTPS, navegador, cookies, persistência e restauração.'
