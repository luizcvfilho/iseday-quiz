.DEFAULT_GOAL := help

.PHONY: help env setup setup-browser setup-browser-deps hooks run up down logs db dev migrate check check-all check-db check-production prod-env prod-build prod-up prod-down prod-logs prod-admin

PROD_ENV_FILE ?= .env.production
PROD_COMPOSE = docker compose --env-file "$(PROD_ENV_FILE)" -f compose.production.yaml

help:
	@printf '%s\n' \
		'make run       Inicia a aplicação com Docker Compose (com build).' \
		'make down      Encerra os containers, preservando os dados.' \
		'make logs      Acompanha os logs dos containers.' \
		'make setup     Instala as dependências para desenvolvimento local.' \
		'make setup-browser Instala o Chromium exigido pelo Playwright.' \
		'make setup-browser-deps Instala Chromium e bibliotecas de sistema (pode exigir sudo).' \
		'make hooks     Instala o hook pre-commit neste clone.' \
		'make dev       Inicia o banco, aplica migrações e inicia frontend/API locais.' \
		'make db        Inicia somente o PostgreSQL e aguarda ficar pronto.' \
		'make migrate   Aplica as migrações na API em execução no Docker.' \
		'make check     Executa as verificações de frontend e backend locais.' \
		'make check-all Executa todas as etapas do pre-commit, sem o ensaio de produção.' \
		'make check-db  Executa os testes de integração PostgreSQL.' \
		'make check-production Testa produção com HTTPS e banco descartável.' \
		'make prod-build Constrói as imagens de produção.' \
		'make prod-up    Inicia produção e aplica migrações antes da API.' \
		'make prod-down  Encerra produção, preservando os dados.' \
		'make prod-logs  Acompanha os logs de produção.' \
		'make prod-admin Cria um administrador em produção (interativo).'

env:
	@test -f .env || cp .env.example .env

setup:
	./scripts/setup.sh

setup-browser:
	npm --prefix frontend run browser:install

setup-browser-deps:
	npm --prefix frontend run browser:install -- --with-deps

hooks:
	uv run --project backend --frozen pre-commit install

run: up

up: env
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs --follow

db: env
	docker compose up -d --wait db

dev: db
	./scripts/dev.sh

migrate:
	docker compose exec api uv run --no-sync alembic upgrade head

check:
	./scripts/check.sh

check-all:
	bash ./scripts/check-all.sh

check-db:
	./scripts/check-db.sh

check-production:
	./scripts/check-production.sh

prod-env:
	@test -f "$(PROD_ENV_FILE)" || { printf '%s\n' 'Copie .env.production.example para $(PROD_ENV_FILE) e preencha os valores. Consulte PRODUCTION.md.'; exit 1; }
	@$(PROD_COMPOSE) config --quiet

prod-build: prod-env
	$(PROD_COMPOSE) build

prod-up: prod-env
	$(PROD_COMPOSE) up --build --detach --wait

prod-down: prod-env
	$(PROD_COMPOSE) down

prod-logs: prod-env
	$(PROD_COMPOSE) logs --follow

prod-admin: prod-env
	$(PROD_COMPOSE) exec api /app/.venv/bin/python -m app.admin create
