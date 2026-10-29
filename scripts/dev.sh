#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
if [[ ! -f .env ]]; then
  echo "Execute ./scripts/setup.sh primeiro."
  exit 1
fi
api_pid=""
frontend_pid=""
cleanup() {
  [[ -z "$api_pid" ]] || kill "$api_pid" 2>/dev/null || true
  [[ -z "$frontend_pid" ]] || kill "$frontend_pid" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT TERM
(cd backend && exec uv run --frozen uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000) &
api_pid=$!
(cd frontend && exec node node_modules/vite/bin/vite.js --host 127.0.0.1 --strictPort) &
frontend_pid=$!
wait -n "$api_pid" "$frontend_pid"
