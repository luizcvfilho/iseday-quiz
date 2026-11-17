#!/usr/bin/env bash
# Pacote mínimo para implantação remota, sem código local nem arquivos privados.
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
mkdir -p dist
package_dir="$(mktemp -d)"
trap 'rm -rf "$package_dir"' EXIT
zip -q -X "$package_dir/iseday-quiz-deploy.zip" \
  Dockerfile.production compose.production.yaml .dockerignore .env.production.example PRODUCTION.md
mv "$package_dir/iseday-quiz-deploy.zip" dist/iseday-quiz-deploy.zip
printf '%s\n' 'Pacote criado: dist/iseday-quiz-deploy.zip'
