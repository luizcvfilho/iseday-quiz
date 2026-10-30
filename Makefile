.DEFAULT_GOAL := help

.PHONY: help env setup run up down logs db dev migrate check check-db

help:
	@printf '%s\n' \
		'make run       Inicia a aplicação com Docker Compose (com build).' \
		'make down      Encerra os containers, preservando os dados.' \
		'make logs      Acompanha os logs dos containers.' \
		'make setup     Instala as dependências para desenvolvimento local.' \
		'make dev       Inicia o banco no Docker e frontend/API locais.' \
		'make db        Inicia somente o PostgreSQL e aguarda ficar pronto.' \
		'make migrate   Aplica as migrações na API em execução no Docker.' \
		'make check     Executa as verificações de frontend e backend locais.' \
		'make check-db  Executa os testes de integração PostgreSQL.'

env:
	@test -f .env || cp .env.example .env

setup:
	./scripts/setup.sh

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

check-db:
	./scripts/check-db.sh
