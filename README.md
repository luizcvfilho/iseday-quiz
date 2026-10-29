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

Executa lint e build do frontend, lint e formatação Python e os testes. Os testes de saúde da API usam conexão simulada. Sem `TEST_DATABASE_URL`, os testes de integração PostgreSQL são marcados como ignorados.

Para validar a migração e as regras de integridade em PostgreSQL 17 real:

```bash
./scripts/check-db.sh
```

O script cria um container temporário, com porta local aleatória e dados em memória, e o remove ao terminar. Não usa o banco nem o volume do Compose. Verifica criação, reversão e reaplicação da migração, correspondência com os modelos, restrições, histórico e concorrência.

Também é possível usar um servidor de teste existente:

```bash
TEST_DATABASE_URL=postgresql+psycopg://usuario:senha@localhost:5432/iseday_test ./scripts/check-db.sh
```

O nome do banco deve terminar em `_test`. Os testes criam e removem apenas esquemas aleatórios próprios; o usuário precisa de permissão para criar esquemas. `REQUIRE_POSTGRES_TESTS=1` faz a ausência de `TEST_DATABASE_URL` falhar em vez de ignorar os testes, para uso em CI.

## Banco e migrações

Os 14 modelos do domínio estão em `backend/app/models.py`. A revisão `0001` cria tabelas, índices, constraints e triggers. As regras SQL dessa revisão ficam em `backend/migrations/versions/0001_integrity.sql`, carregadas pela migração; ambos os arquivos devem ser distribuídos juntos. Não use `create_all` nem execute `docs/database-schema.sql`: esse arquivo é a proposta original, não uma migração.

Para preparar um banco vazio ou atualizar o banco local:

```bash
cd backend
uv run --frozen alembic upgrade head
uv run --frozen alembic current
```

No Compose: `docker compose exec api uv run --no-sync alembic upgrade head`.

A migração exige PostgreSQL e não importa conteúdo nem cria contas administrativas. Ela preserva versões publicadas, exige 25 escolhas únicas da mesma versão e resultados de todas as áreas/cursos na submissão, e bloqueia edições posteriores das respostas e resultados. O cadastro fica imutável após envio, com exceção dos campos necessários à sessão e à conclusão. O feedback só aceita um curso sugerido, quando há concordância. A exclusão da participação inteira remove seus dados dependentes; os registros de auditoria podem sobreviver à exclusão.

O motor de cálculo está em `backend/app/scoring.py`. A integração com a API e as operações atômicas de submissão/feedback ainda serão implementadas. As triggers usam bloqueios da versão/participação para serializar alterações concorrentes. O catálogo pode ser arquivado sem impedir que participações já iniciadas terminem.

Para futuras alterações, edite os modelos e gere uma nova revisão com `uv run --frozen alembic revision --autogenerate -m "descricao"`. Revise o código gerado: funções/triggers e algumas mudanças de constraints exigem migrações manuais. Não edite revisões já aplicadas. A reversão para `base` remove todas as tabelas do domínio e seus dados; use-a somente em banco descartável ou em procedimento de manutenção planejado.

`docker compose down` encerra os serviços e preserva os dados. O volume `postgres_data` guarda o PostgreSQL. As variáveis `POSTGRES_*` inicializam apenas um volume vazio: alterar o `.env` não troca as credenciais de um banco já criado.

## Estrutura

```text
frontend/             React, TypeScript, Vite e React Router
backend/app/          FastAPI, configuração e conexão SQLAlchemy/Psycopg
backend/migrations/   Migrações Alembic e regras de integridade versionadas
backend/tests/        Testes da API e integração PostgreSQL em postgres/
scripts/              Setup, desenvolvimento e verificações
compose.yaml          PostgreSQL, API e frontend em desenvolvimento
```

As dependências de backend incluem validação de e-mail e Argon2 para a futura autenticação administrativa, além de openpyxl para a importação do catálogo. O fluxo do aluno e o login ainda não foram implementados.

## Catálogo do quiz

A cópia original da planilha está em `backend/catalog/quiz-final.xlsx`. O catálogo normalizado, o SHA-256 da fonte e as pendências de revisão estão em `backend/catalog/quiz-final.json`: **74 afirmativas, 11 cursos, 5 áreas e 96 vínculos**, com peso proposto de 1 por vínculo. Os textos originais são preservados, inclusive possíveis erros de digitação.

Valide sem precisar de banco (comandos a partir da raiz):

```bash
cd backend
uv run --frozen python -m app.catalog validate
# Opcional: regenerar o relatório de revisão versionado.
uv run --frozen python -m app.catalog validate --report catalog/quiz-final.json
```

Depois de aplicar as migrações, importe no banco configurado em `DATABASE_URL` (ainda em `backend/`):

```bash
uv run --frozen alembic upgrade head
uv run --frozen python -m app.catalog import --version 1
```

No Compose, após reconstruir a imagem da API com as novas dependências:

```bash
docker compose up -d --build api
docker compose exec api uv run --no-sync alembic upgrade head
docker compose exec api uv run --no-sync python -m app.catalog import --version 1
```

O comando grava **somente um rascunho**, em uma única transação. Repetir a mesma importação para a mesma versão retorna o registro existente; conteúdo diferente é rejeitado sem sobrescrever dados. Use outro número de versão para uma revisão. Importações concorrentes são serializadas. Versões publicadas ou arquivadas nunca são alteradas ou republicadas pelo importador.

O importador exige o modelo das duas abas da planilha e rejeita fórmulas, números ou frases duplicados, cursos desconhecidos, vínculos repetidos e conteúdo incompleto. `--file /caminho/planilha.xlsx` permite validar uma revisão com a mesma estrutura; `--event "Nome do evento"` define o evento na importação.

Antes de publicar, a instituição precisa validar os textos, a metodologia, os pesos e os destinos. As listas de espaços são referências por área, sem destinos específicos inventados para os cursos. Consulte as pendências em `backend/catalog/quiz-final.json`. O importador não publica versões.

## Cálculo de afinidade

`calculate_scores`, em `backend/app/scoring.py`, recebe um `ScoringCatalog` com o retrato de uma versão e exatamente 25 UUIDs de afirmativas únicas dessa versão. O chamador deve montar esse retrato com todas as áreas, cursos, afirmativas e pesos da versão vinculada à participação. O motor não acessa o banco nem publica conteúdo.

O método `area_distinct_count_course_sum_v1` soma um ponto por área distinta em cada afirmativa e soma os pesos positivos dos vínculos para cada curso. Todas as áreas com a maior pontuação vencem; dentro de cada área vencedora, todos os cursos com a maior pontuação positiva são recomendados. Os pontos não são normalizados nem apresentados como percentuais.

O resultado contém o identificador da versão e pontuações/indicadores de todas as áreas e cursos, inclusive os com zero. A ordem dos identificadores é estável e não desempata resultados. Escolhas inválidas geram `InvalidSelectionError`; catálogo inconsistente ou método desconhecido gera `ScoringConfigurationError`, sem produzir resultado parcial.

Para executar somente os testes do cálculo, a partir da raiz:

```bash
uv run --project backend --frozen pytest backend/tests/test_scoring.py
```

Os testes cobrem limites, duplicatas, identificadores externos à versão, vínculos inválidos, pesos, empates, ausência de normalização e o catálogo original de 74 afirmativas. O motor implementa a regra proposta; sua aprovação institucional continua pendente.

## Próximas etapas

1. Revisar o catálogo importável e validar conteúdo, metodologia e destinos com a instituição.
2. Integrar o motor de cálculo à API e implementar o fluxo do aluno com persistência.
3. Implementar autenticação e consultas administrativas.

Antes da publicação, validar o conteúdo e a metodologia do quiz.

## Referências

- [Node.js](https://nodejs.org/en/download)
- [Vite](https://vite.dev/guide/)
- [Ambiente Python no FastAPI](https://fastapi.tiangolo.com/virtual-environments/)
- [Instalação do uv](https://docs.astral.sh/uv/getting-started/installation/)
- [Instalação do Docker](https://docs.docker.com/get-started/get-docker/)
