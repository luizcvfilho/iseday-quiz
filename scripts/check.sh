#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
npm --prefix frontend run lint
npm --prefix frontend run build
uv run --project backend --frozen ruff check backend
uv run --project backend --frozen ruff format --check backend
uv run --project backend --frozen pytest backend/tests
