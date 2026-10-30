#!/usr/bin/env bash
# Runs a command with a test PostgreSQL database, independently of .env/Compose.
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ "$#" == 0 ]]; then
  printf '%s\n' 'Uso: scripts/with-test-db.sh COMANDO [ARGUMENTOS...]' >&2
  exit 2
fi

container_id=""
cleanup() {
  if [[ -n "$container_id" ]]; then
    docker rm --force --volumes "$container_id" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ -z "${TEST_DATABASE_URL:-}" ]]; then
  container_id="$(docker run --rm --detach \
    --env POSTGRES_DB=iseday_test \
    --env POSTGRES_USER=iseday \
    --env POSTGRES_PASSWORD=iseday_test \
    --publish 127.0.0.1::5432 \
    --mount type=tmpfs,destination=/var/lib/postgresql/data \
    postgres:17)"

  ready=false
  for ((attempt = 0; attempt < 30; attempt++)); do
    if docker exec "$container_id" pg_isready \
      --host=127.0.0.1 --username=iseday --dbname=iseday_test >/dev/null; then
      ready=true
      break
    fi
    sleep 1
  done
  if [[ "$ready" != true ]]; then
    docker logs "$container_id"
    exit 1
  fi

  published_address="$(docker port "$container_id" 5432/tcp)"
  export TEST_DATABASE_URL="postgresql+psycopg://iseday:iseday_test@127.0.0.1:${published_address##*:}/iseday_test"
fi

export REQUIRE_POSTGRES_TESTS=1
"$@"
