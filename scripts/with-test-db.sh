#!/usr/bin/env bash
# Runs a command with a test MySQL database, independently of .env/Compose.
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
    --env MYSQL_DATABASE=iseday_test \
    --env MYSQL_ROOT_PASSWORD=iseday_test \
    --env MYSQL_ROOT_HOST=% \
    --publish 127.0.0.1::3306 \
    --mount type=tmpfs,destination=/var/lib/mysql \
    mysql:8.4 --log-bin-trust-function-creators=ON)"

  ready=false
  for ((attempt = 0; attempt < 60; attempt++)); do
    if docker exec -e MYSQL_PWD=iseday_test "$container_id" mysql \
      -h 127.0.0.1 -u root iseday_test -e 'SELECT 1' >/dev/null 2>&1; then
      ready=true
      break
    fi
    sleep 1
  done
  if [[ "$ready" != true ]]; then
    docker logs "$container_id"
    exit 1
  fi

  published_address="$(docker port "$container_id" 3306/tcp)"
  export TEST_DATABASE_URL="mysql+pymysql://root:iseday_test@127.0.0.1:${published_address##*:}/iseday_test"
fi

export REQUIRE_MYSQL_TESTS=1
"$@"
