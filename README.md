# ISE Day Quiz

Base de desenvolvimento do quiz de afinidades: React + TypeScript + Vite, FastAPI e PostgreSQL.

## Pré-requisitos

- **Node.js 24** com npm (versão registrada em `.nvmrc`).
- **uv** para gerenciar Python 3.13, ambiente virtual e dependências.
- **Docker com Compose** para executar o PostgreSQL 17 ou a aplicação completa.

Para executar toda a aplicação em containers, apenas Docker com Compose é necessário. No desenvolvimento local, mantenha também Node.js, npm e uv disponíveis no PATH. Execute os comandos a partir da raiz do repositório, salvo indicação contrária.

O uv instala a versão de Python definida em `backend/.python-version` quando necessário.

## Início rápido com Docker

```bash
cp .env.example .env
# Revise as configurações locais antes de iniciar.
docker compose up --build
```

- Frontend: <http://localhost:5173>
- Documentação da API: <http://localhost:8000/api/docs>
- API ativa: <http://localhost:8000/api/health>
- API com conexão ao banco: <http://localhost:8000/api/health/ready>

Os serviços são publicados somente em `127.0.0.1`. O Compose serve para desenvolvimento; configuração de produção e HTTPS serão tratados em outra etapa. As credenciais de exemplo são exclusivamente locais. Senhas com caracteres reservados de URL precisam de codificação na `DATABASE_URL` (inclusive no Compose).

## Desenvolvimento local

```bash
./scripts/setup.sh
# Instala com package-lock.json e uv.lock; cria .env se ainda não existir.
docker compose up -d db
./scripts/dev.sh
```

O último comando inicia Vite e Uvicorn com recarregamento automático. `Ctrl+C` encerra ambos. O Vite encaminha `/api` para a API, mantendo a mesma origem no navegador. Não use `vite preview` como servidor integrado: esse proxy é de desenvolvimento; a publicação precisará encaminhar `/api` no servidor web.

A API pode iniciar sem o PostgreSQL: `/api/health` retorna 200; `/api/health/ready` retorna 503 enquanto o banco não estiver acessível.

Para executar frontend e API separadamente:

```bash
(cd backend && uv run --frozen uvicorn app.main:create_app --factory --reload)
# Em outro terminal, também a partir da raiz:
npm --prefix frontend run dev
```

O arquivo `.env` fica na raiz e não é versionado. `DATABASE_URL` configura a API local; no Compose o host do banco é substituído por `db`. Ao mudar `POSTGRES_PORT`, ajuste também a porta em `DATABASE_URL`. Variáveis de ambiente do processo têm precedência. Nunca coloque segredos em variáveis `VITE_*`, pois elas são públicas no navegador.

## Verificações

```bash
./scripts/check.sh
```

Executa lint e build do frontend, lint e formatação Python e testes da API. Os testes usam configuração própria e substituem a conexão por um mock: não acessam o banco de desenvolvimento e não substituem testes de integração com PostgreSQL.

## Banco e migrações

SQLAlchemy e Alembic estão configurados, com sessões por requisição e verificação real de conexão via `SELECT 1`. As tabelas do domínio e a migração inicial ainda serão implementadas. Não use `create_all` nem scripts de inicialização paralelos às migrações.

Depois de implementar e importar os modelos em `backend/migrations/env.py`:

```bash
cd backend
uv run --frozen alembic revision --autogenerate -m "initial schema"
# Revisar o arquivo gerado antes de aplicar, incluindo constraints e triggers.
uv run --frozen alembic upgrade head
```

No Compose, quando as revisões existirem: `docker compose exec api uv run --no-sync alembic upgrade head`.

`docker compose down` encerra os serviços e preserva os dados. O volume `postgres_data` guarda o PostgreSQL. As variáveis `POSTGRES_*` inicializam apenas um volume vazio: alterar o `.env` não troca as credenciais de um banco já criado.

## Estrutura

```text
frontend/             React, TypeScript, Vite e React Router
backend/app/          FastAPI, configuração e conexão SQLAlchemy/Psycopg
backend/migrations/   Ambiente Alembic para futuras migrações
backend/tests/        Testes isolados da API
scripts/              Setup, desenvolvimento e verificações
compose.yaml          PostgreSQL, API e frontend em desenvolvimento
```

As dependências de backend incluem validação de e-mail e Argon2 para a futura autenticação administrativa. O quiz, a importação do catálogo e o login ainda não foram implementados.

## Próximas etapas

1. Implementar modelos e migração inicial a partir do esquema revisado.
2. Importar e validar o catálogo de afirmativas, cursos e áreas.
3. Implementar o fluxo do aluno, cálculo com empates e persistência.
4. Implementar autenticação e consultas administrativas.

Antes da publicação, validar o conteúdo e a metodologia do quiz.

## Referências

- [Node.js](https://nodejs.org/en/download)
- [Vite](https://vite.dev/guide/)
- [Ambiente Python no FastAPI](https://fastapi.tiangolo.com/virtual-environments/)
- [Instalação do uv](https://docs.astral.sh/uv/getting-started/installation/)
- [Instalação do Docker](https://docs.docker.com/get-started/get-docker/)
