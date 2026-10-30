#!/usr/bin/env bash
# Exibe as mesmas etapas individuais do pre-commit, sem duplicar sua definição.
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

exec uv run --project backend --frozen pre-commit run --all-files "$@"
