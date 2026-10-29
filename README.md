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

O motor de cálculo está em `backend/app/scoring.py`, integrado à submissão atômica em `backend/app/participants/`. A confirmação e o encaminhamento também são gravados de forma atômica. As triggers usam bloqueios da versão/participação para serializar alterações concorrentes. O catálogo pode ser arquivado sem impedir que participações já iniciadas submetam suas escolhas e confirmem seus resultados.

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

As dependências de backend incluem validação de e-mail, Argon2 para a futura autenticação administrativa e openpyxl para a importação do catálogo. A API do aluno já oferece cadastro, sessão, submissão, resultado, confirmação e encaminhamento; as telas e o login administrativo ainda serão implementados.

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

## API do participante

As rotas ficam sob a mesma origem do frontend, usando o proxy `/api`. O cadastro exige uma versão publicada e escolas ativas já cadastradas no banco. O importador continua criando somente rascunhos: esta etapa não publica o catálogo nem cadastra escolas automaticamente.

Configure `PRIVACY_NOTICE_VERSION` e `PRIVACY_NOTICE_TEXT` no `.env`. O exemplo fornecido é somente para desenvolvimento com dados fictícios; substitua-o pelo aviso institucional aprovado antes do uso real. Sem ambos, a consulta do quiz e novos cadastros retornam 503. A versão apresentada precisa ser enviada no cadastro; ela registra qual aviso foi exibido, sem representar consentimento por si só.

| Método e rota | Comportamento |
|---|---|
| `GET /api/quiz/current` | Versão publicada, aviso e afirmativas ordenadas, sem vínculos ou pesos. |
| `GET /api/schools?q=nome&limit=50` | Escolas ativas; busca por nome e limite de 1 a 100 registros. |
| `POST /api/participations` | Cadastro validado, participação em rascunho e cookie temporário. |
| `GET /api/participations/me` | Identificador, versão, estado e expiração da própria sessão, sem contatos. |
| `POST /api/participations/me/submit` | Valida 25 escolhas, calcula e grava escolhas/resultados na mesma transação. |
| `GET /api/participations/me/result` | Resultado persistido da própria participação, com todas as áreas/cursos, empates e eventual confirmação. |
| `POST /api/participations/me/feedback` | Registra concordância, curso escolhido e destino exibido; conclui a participação na mesma transação. |
| `POST /api/participations/me/end` | Revoga a credencial e remove o cookie; preserva o registro e as respostas. |

Todos os POSTs exigem o cabeçalho `X-Quiz-Request: 1`. A API recusa requisições com `Sec-Fetch-Site: cross-site` e não habilita CORS. Esse cabeçalho personalizado é a proteção de CSRF para a API de mesma origem; qualquer futura abertura de CORS precisa preservar essa proteção. Referência: [OWASP — cabeçalhos personalizados para APIs](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html#employing-custom-request-headers-for-ajaxapi).

Exemplo do corpo do cadastro (substitua os UUIDs pelos valores de `/api/quiz/current` e `/api/schools`):

```json
{
  "quiz_version_id": "00000000-0000-0000-0000-000000000001",
  "school_id": "00000000-0000-0000-0000-000000000002",
  "full_name": "Aluno de teste",
  "phone": "+5511999999999",
  "email": "aluno@example.org",
  "privacy_notice_version": "development-v1"
}
```

O cadastro retorna 201 com metadados da participação. O cookie é `HttpOnly`, `SameSite=Strict`, sem `Domain`, válido por 60 minutos por padrão (`PARTICIPANT_SESSION_MINUTES`, de 1 a 240). Em produção (`APP_ENV=production`), usa `Secure` e o nome `__Host-iseday_participant`; em desenvolvimento, `iseday_participant`. O token aleatório só aparece no cookie; o banco guarda seu SHA-256. Envie o cookie nas chamadas seguintes e nunca use o UUID como credencial.

O envio recebe `{"statement_ids": ["uuid-1", "uuid-2", "..."]}`, com exatamente 25 UUIDs únicos da versão da participação. A API bloqueia a participação até o fim da transação. O mesmo conjunto de escolhas, em qualquer ordem, retorna o resultado salvo sem recalcular; outro conjunto após submissão retorna 409. Uma versão arquivada continua válida para quem já havia iniciado. Qualquer falha durante a gravação desfaz escolhas, pontuações e mudança de estado.

Repetir um cadastro idêntico com o cookie válido retorna 200 e a mesma participação. Dados diferentes na mesma sessão retornam 409: encerre-a antes do próximo aluno. Sem cookie não há deduplicação automática por contato. Uma sessão ausente, expirada ou revogada recebe 401; resultado ainda não submetido recebe 409. O encerramento é idempotente e retorna 204 mesmo sem sessão válida. A resposta de resultado inclui escolhas, pontuações e indicadores, sem contatos, pesos ou percentuais.

Para confirmar, envie um booleano JSON e, em caso de concordância, o UUID de um dos cursos marcados com `is_recommended: true` no resultado:

```json
{
  "agrees_with_result": true,
  "chosen_course_id": "00000000-0000-0000-0000-000000000003"
}
```

Para discordar, envie `{"agrees_with_result": false}`; o curso deve estar ausente ou ser `null`. Valores como `"false"` e `1` não são aceitos como booleanos. Concordância sem curso, discordância com curso, curso não sugerido e tentativa de informar um destino no corpo retornam 422. Todos os cursos sugeridos em áreas empatadas são elegíveis.

No “sim”, o encaminhamento usa o destino e as instruções específicos do curso, quando cadastrados; caso contrário, usa o par da área. No “não”, usa o destino e as instruções de Psicologia/SPA da versão respondida, mesmo que outra versão já esteja publicada. Os textos são copiados exatamente do catálogo, sem inferir laboratórios ou localizações.

O POST de feedback retorna 200 com `participation_id`, `status: "completed"`, `completed_at`, `agrees_with_result`, `chosen_course_id`, `destination`, `destination_instructions` e `answered_at`. Feedback e conclusão são gravados na mesma transação, sem mudar escolhas ou pontuações. Repetir a mesma resposta e curso devolve a confirmação anterior, com os mesmos textos e horários. Uma resposta ou curso diferente após conclusão retorna 409; antes da submissão também retorna 409.

`GET /api/participations/me/result` inclui `feedback: null` enquanto aguarda a confirmação e o objeto da confirmação após concluir. O destino é recuperado do registro salvo. A sessão continua válida até expirar ou chamar `/api/participations/me/end`, permitindo recuperar a orientação e repetir uma requisição que perdeu a resposta. Após exibir o encaminhamento, o frontend deve chamar o encerramento e limpar seu estado para o próximo aluno; a conclusão, sozinha, não revoga a sessão.

As respostas `/api/` usam `Cache-Control: no-store`; erros de validação omitem os valores enviados e falhas de banco retornam mensagem genérica. Há limites por IP em janelas de 60 segundos: `PARTICIPANT_REGISTRATION_LIMIT` (60) para cadastro e `PARTICIPANT_SUBMISSION_LIMIT` (120) para cada uma das operações de submissão e feedback, em janelas separadas. Cada operação também permite 30 tentativas por credencial por minuto. O excesso retorna 429 com `Retry-After`. O controle usa memória limitada por processo; implantações com múltiplos workers precisam de limite compartilhado no proxy. Configure proxies confiáveis no servidor antes de usar IPs encaminhados.

Os testes PostgreSQL exercitam as rotas com banco real, rollback, isolamento de sessões, expiração, revogação, arquivo de versões, destinos de curso/área/SPA, submissões e confirmações concorrentes. Execute-os com `./scripts/check-db.sh` ou com `TEST_DATABASE_URL` apontando para um banco descartável cujo nome termine em `_test`.

## Próximas etapas

1. Revisar o catálogo importável e validar conteúdo, metodologia e destinos com a instituição.
2. Implementar as telas do fluxo do aluno, integradas à API.
3. Implementar autenticação e consultas administrativas.

Antes da publicação, validar o conteúdo e a metodologia do quiz.

## Referências

- [Node.js](https://nodejs.org/en/download)
- [Vite](https://vite.dev/guide/)
- [Ambiente Python no FastAPI](https://fastapi.tiangolo.com/virtual-environments/)
- [Instalação do uv](https://docs.astral.sh/uv/getting-started/installation/)
- [Instalação do Docker](https://docs.docker.com/get-started/get-docker/)
