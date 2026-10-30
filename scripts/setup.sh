#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
for tool in node npm uv; do
  if ! command -v "$tool" >/dev/null; then
    echo "Ferramenta ausente: $tool. Consulte o README.md."
    exit 1
  fi
done
if [[ ! -f .env ]]; then
  cp .env.example .env
fi
npm --prefix frontend ci
uv sync --project backend --frozen
uv run --project backend --frozen pre-commit install
npm --prefix frontend run browser:install
echo "Dependencias, hook pre-commit e Chromium instalados. Inicie o banco com docker compose up -d db."
