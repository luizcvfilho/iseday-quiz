#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
exec bash scripts/with-test-db.sh uv run --project backend --frozen pytest backend/tests/mysql "$@"
