# ISE Day Quiz

Quiz de afinidades: React + TypeScript + Vite, FastAPI e MySQL.

Para produção, consulte [PRODUCTION.md](PRODUCTION.md): imagens sem servidor de desenvolvimento, HTTPS, migrações, administração, backup e ensaio com banco descartável. Os comandos de desenvolvimento abaixo continuam independentes.

## Pré-requisitos

- **Node.js 24** com npm (versão registrada em `.nvmrc`).
- **uv** para gerenciar Python 3.13, ambiente virtual e dependências.
- **Docker com Compose** para executar o MySQL 8.4 ou a aplicação completa.

Para executar toda a aplicação em containers, apenas Docker com Compose é necessário. No desenvolvimento local, mantenha também Node.js, npm e uv disponíveis no PATH. Execute os comandos a partir da raiz do repositório, salvo indicação contrária.

O uv instala a versão de Python definida em `backend/.python-version` quando necessário.

## Comandos com Make

Com GNU Make instalado, execute na raiz do repositório:

```bash
make run
```

Esse comando cria `.env` a partir de `.env.example` se necessário e inicia MySQL, API e frontend com Docker Compose, reconstruindo as imagens. Revise as configurações locais antes de iniciar. O frontend fica em <http://localhost:5173> e a documentação da API em <http://localhost:8000/api/docs>. Use `make down` para encerrar os containers preservando os dados e `make logs` para acompanhar os logs. `make up` é um alias de `make run`.

Em outro terminal, com a API em execução, aplique as migrações com `make migrate`. A preparação do catálogo e da conta administrativa segue as instruções das seções abaixo.

Para desenvolvimento local, com Node.js, npm, uv e Docker disponíveis:

```bash
make setup
make dev
```

`make setup` instala as dependências, o Chromium e o hook pre-commit neste clone, e cria `.env` se necessário. `make dev` inicia o MySQL no Docker, aguarda o banco ficar pronto, aplica as migrações pendentes em `DATABASE_URL` e executa frontend e API locais com recarregamento automático. Se a migração falhar, os servidores não são iniciados. `Ctrl+C` encerra esses dois processos. Use `make down` para encerrar também o banco.

`make check` executa as verificações existentes e `make check-db` executa os testes de integração MySQL. `make` ou `make help` lista os comandos disponíveis.

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

Os serviços são publicados somente em `127.0.0.1`. Este Compose serve para desenvolvimento; use `compose.production.yaml` e siga [PRODUCTION.md](PRODUCTION.md) para produção com HTTPS. As credenciais de exemplo são exclusivamente locais. Senhas com caracteres reservados de URL precisam de codificação na `DATABASE_URL` (inclusive no Compose).

## Desenvolvimento local

```bash
./scripts/setup.sh
# Instala dependências, Chromium e pre-commit; cria .env se ainda não existir.
docker compose up -d --wait db
./scripts/dev.sh
```

O último comando aplica as migrações pendentes antes de iniciar Vite e Uvicorn com recarregamento automático. O banco precisa estar acessível; uma falha nas migrações interrompe a inicialização. `Ctrl+C` encerra ambos. O Vite encaminha `/api` para a API, mantendo a mesma origem no navegador. Não use `vite preview` como servidor integrado: esse proxy é de desenvolvimento; em produção, o Caddy encaminha `/api` no servidor web.

A API pode iniciar sem o MySQL: `/api/health` retorna 200; `/api/health/ready` retorna 503 enquanto o banco não estiver acessível.

Para executar frontend e API separadamente:

```bash
(cd backend && uv run --frozen uvicorn app.main:create_app --factory --reload)
# Em outro terminal, também a partir da raiz:
npm --prefix frontend run dev
```

O arquivo `.env` fica na raiz e não é versionado. `DATABASE_URL` configura a API local; no Compose o host do banco é substituído por `db`. Ao mudar `MYSQL_PORT`, ajuste também a porta em `DATABASE_URL`. Quem já tem um `.env` da versão com PostgreSQL deve atualizar as chaves de banco conforme `.env.example`, preservando as demais configurações. O Compose cria um volume MySQL separado. Variáveis de ambiente do processo têm precedência. Nunca coloque segredos em variáveis `VITE_*`, pois elas são públicas no navegador.

## Verificações

O workflow [CI](.github/workflows/ci.yml) executa automaticamente em pushes e pull requests, e também pode ser iniciado manualmente na aba Actions do GitHub. Os jobs verificam:

- Oxlint, Ruff e formatação Python.
- Todos os testes do backend, incluindo integração com MySQL 8.4 obrigatório.
- Build/TypeScript e testes Chromium do frontend, tanto no build quanto com API e MySQL reais.
- O ensaio de produção com Docker/HTTPS, persistência e backup/restauração (`make check-production`).

O CI usa Node.js de `.nvmrc`, Python de `backend/.python-version` e instalações pelos lockfiles. Os bancos e containers são descartáveis, com dados fictícios; não é necessário configurar secrets ou arquivos `.env`. Em falhas de navegador, os traces ficam disponíveis como artifacts por sete dias.

O [pre-commit](.pre-commit-config.yaml) executa lint, tipos, build e testes de backend/frontend antes de cada commit, sobre todo o projeto, e bloqueia o commit em caso de falha. O ensaio de produção com Docker/HTTPS é executado automaticamente apenas no CI do GitHub. Cada etapa local aparece separadamente com seu próprio resultado; as etapas seguintes continuam sendo executadas mesmo quando uma falha:

| ID do hook | Verificação |
| --- | --- |
| `frontend-lint` | Lint do frontend com Oxlint |
| `backend-lint` | Lint do backend com Ruff |
| `backend-format` | Formatação Python, sem modificar arquivos |
| `frontend-typecheck` | Tipos do frontend, configuração e testes Playwright |
| `frontend-build` | Build do frontend com Vite |
| `backend-tests` | Testes unitários do backend |
| `backend-mysql-tests` | Testes de integração com MySQL real |
| `frontend-tests` | Testes Chromium sobre o build já gerado |
| `frontend-live-tests` | Fluxo de navegador com API e MySQL reais |

Tipos e build são executados uma vez antes dos testes de interface. A etapa de integração de navegador executa somente `live.spec.ts`; os demais cenários ficam na etapa de frontend. No CI, o ensaio Docker constrói suas próprias imagens de produção; ele também pode ser iniciado manualmente com `make check-production`.

O hook é instalado por `make setup`. Para ativá-lo em um clone já preparado, instale também o Chromium da versão atual do Playwright:

```bash
uv sync --project backend --frozen
make setup-browser
make hooks
```

Para executar todas as etapas manualmente, use `make check-all` ou `uv run --project backend --frozen pre-commit run --all-files`. Para ver também a saída das etapas aprovadas, use `bash scripts/check-all.sh --verbose`. Para executar um hook isolado, por exemplo os testes do MySQL:

```bash
uv run --project backend --frozen pre-commit run backend-mysql-tests --all-files
```

Ao executar `frontend-tests` isoladamente, gere o build antes com `npm --prefix frontend run build`; na execução completa, o hook `frontend-build` já faz isso.

A suíte local exige Node.js, npm, uv, Docker e Chromium do Playwright. Sem `TEST_DATABASE_URL`, as etapas MySQL e de integração do navegador criam e removem seus próprios bancos temporários. As portas 5179 e 8009 precisam estar livres. Tanto o pre-commit quanto `make check-all` deixam o ensaio de produção fora da execução local automática.

Se aparecer `Executable doesn't exist ... chromium_headless_shell`, execute `make setup-browser` no mesmo ambiente em que roda o Git/pre-commit (por exemplo, dentro do WSL). Repita após atualizar o Playwright, pois cada versão exige seus próprios binários. Se faltarem bibliotecas de sistema em Linux, execute `make setup-browser-deps` em um terminal interativo; a instalação pode solicitar a senha do sudo. Confira `PLAYWRIGHT_BROWSERS_PATH` se tiver personalizado o cache. Antes de cada suíte de navegador, o projeto tenta iniciar o Chromium e informa a correção necessária uma única vez por suíte, em vez de falhar em todos os cenários.

Para executar as verificações localmente:

```bash
./scripts/check.sh
```

Executa lint e build do frontend, lint e formatação Python e os testes. Os testes de saúde da API usam conexão simulada. Sem `TEST_DATABASE_URL`, os testes de integração MySQL são marcados como ignorados.

Para validar a migração e as regras de integridade em MySQL 8.4 real:

```bash
./scripts/check-db.sh
```

O script cria um container temporário, com porta local aleatória e dados em memória, e o remove ao terminar. Não usa o banco nem o volume do Compose. Verifica instalação do catálogo fixo, rollback dos dados se a carga inicial falhar, correspondência com os modelos, restrições e concorrência.

Também é possível usar um servidor de teste existente:

```bash
TEST_DATABASE_URL=mysql+pymysql://usuario:senha@localhost:3306/iseday_test ./scripts/check-db.sh
```

O nome do banco deve terminar em `_test` e ter até 29 letras, dígitos ou sublinhados. Os testes criam e removem bancos com um sufixo aleatório, sem alterar a base indicada na URL. Use uma instância descartável e uma conta que possa criar e remover esses bancos, instalar tabelas e gatilhos e gravar dados. `REQUIRE_MYSQL_TESTS=1` faz a ausência de `TEST_DATABASE_URL` falhar em vez de ignorar os testes, para uso em CI.

## Estrutura

```text
frontend/             React, TypeScript, Vite e React Router
backend/app/          FastAPI, configuração e conexão SQLAlchemy/PyMySQL
backend/migrations/   Migrações Alembic e regras de integridade versionadas
backend/tests/        Testes da API e integração MySQL em mysql/
scripts/              Setup, desenvolvimento e verificações
compose.yaml          MySQL, API e frontend em desenvolvimento
```

As dependências de backend incluem validação de e-mail, Argon2 para a autenticação administrativa e openpyxl para a validação da planilha do catálogo. O fluxo do aluno oferece telas e API de cadastro, sessão, submissão, resultado, confirmação e encaminhamento. A área administrativa oferece login, filtros, resumo e consulta individual dos resultados.

## Telas do aluno

Abra <http://localhost:5173> após iniciar os serviços. O fluxo apresenta cadastro, escolha das afirmativas, revisão das 25 escolhas, resultado com todos os empates, confirmação e encaminhamento. O contador permanece visível; com 25 escolhas, novas marcações são bloqueadas até desmarcar uma. O envio fica disponível somente com exatamente 25 escolhas únicas.

Todas as telas usam Material UI, incluindo cadastro, escolhas, revisão, resultado, encaminhamento, retomada, erros e página não encontrada. O tema compartilhado fica em `frontend/src/theme.ts`, com `ThemeProvider`, `CssBaseline` e componentes localizados em português. O CSS global fica restrito ao atalho de navegação por teclado; estilos de componentes e layouts usam o tema e `sx`.

A referência visual é a [página inicial do ISECENSA](https://www.isecensa.edu.br/), consultada em 29/10/2026: azul `#006aa3`, azul-marinho `#0b172b`, rodapé `#001a33`, fundos brancos e detalhes dourados. Inter no texto e Open Sans nos títulos são servidas localmente por Fontsource; suas licenças acompanham o build em `frontend/public/licenses/`. O brasão em `frontend/public/brand/brasao-isecensa.png` foi obtido do [arquivo publicado no site institucional](https://www.isecensa.edu.br/sites/default/files/BRAS%C3%83O%20COLOR.png). O tema adapta essas referências ao quiz; ajustes futuros de marca devem ser feitos nesse tema central.

A escola é um campo de texto obrigatório: o participante digita o nome livremente, com até 200 caracteres. O nome é salvo na própria participação, sem espaços nas extremidades, e continua disponível no histórico, nos filtros, nos resumos e no CSV. Não é necessário cadastrar escolas antecipadamente. O telefone aceita formatação brasileira com DDD e é enviado no formato `+55…`. O aviso configurado pela instituição aparece antes do cadastro. Se o catálogo fixo ou o aviso ainda não estiverem preparados, a interface informa a indisponibilidade e permite tentar novamente.

Contatos e marcações ficam apenas na memória da página, sem `localStorage` ou `sessionStorage`. Os contatos saem da tela após iniciar o quiz. Marcações ainda não enviadas se perdem ao recarregar; há aviso ao tentar sair com escolhas e informação explícita na retomada do rascunho. Uma sessão existente permite retomar a própria participação e consultar o resultado e o encaminhamento. A retomada usa o mesmo catálogo fixo de todas as participações.

Na tela inicial de retomada, **Fazer novo teste** encerra a sessão atual e abre um cadastro vazio, preservando a participação anterior. No cadastro, o e-mail e o telefone são consultados ao sair dos campos e novamente antes do envio. Se algum deles já foi utilizado, a interface informa se a participação está em andamento ou concluída e pergunta se o aluno quer continuar ou fazer um novo teste. A retomada busca a participação mais recente que corresponda a pelo menos um dos contatos, sem diferenciar maiúsculas e minúsculas no e-mail. O aluno recebe uma nova sessão; contatos, escolhas e resultados anteriores permanecem salvos. Rascunhos retomam a tela do quiz, resultados submetidos retomam a confirmação e participações concluídas retomam o encaminhamento.

Se a resposta de um envio se perder, a interface consulta o resultado salvo. Se também não conseguir confirmar essa consulta, mantém as escolhas e bloqueia sua edição até recuperar a resposta ou repetir o mesmo envio. Confirmações usam a mesma regra.

### Testes da interface

Instale o Chromium de teste uma vez e execute os cenários de navegador:

```bash
cd frontend
npx playwright install chromium
npm test
# Os mesmos cenários com os arquivos do build de produção:
npm run test:build
```

Em Linux sem bibliotecas do Chromium, prepare as dependências indicadas pelo Playwright (`npx playwright install --with-deps chromium`). Os testes usam servidores temporários locais e dados fictícios. Os cenários incluem Autocomplete, teclado, limite/edição de escolhas, empates, falhas de conexão, reenvio, retomada, expiração, preservação dos dados durante pausas, página não encontrada e layout móvel. `./scripts/check.sh` mantém as verificações de lint/build/backend; os testes de navegador são executados separadamente. O build separa React e Material UI em arquivos próprios para cache e mantém os pesos/subconjuntos de fonte usados pela interface.

Para testar também o fluxo com API real, catálogo original e MySQL, configure um banco de teste cujo nome termine em `_test`:

```bash
TEST_DATABASE_URL=mysql+pymysql://usuario:senha@localhost:3306/iseday_test npm run test:live
```

Esse comando também exige `uv` no PATH. O servidor de teste cria um esquema aleatório próprio, aplica a migração, instala o catálogo fixo **somente nesse esquema de teste** e usa os nomes de escola digitados durante o teste. O esquema é removido ao encerrar. Não usa o banco da aplicação nem altera o catálogo dela. As portas 5179 (Vite) e 8009 (API de teste) precisam estar livres. Capturas e traces de teste ficam em `frontend/test-results/`, fora do Git.

## Catálogo do quiz

A planilha do catálogo está em `backend/catalog/quiz-final.xlsx`. O catálogo normalizado, o SHA-256 da fonte e as pendências de revisão estão em `backend/catalog/quiz-final.json`: **74 afirmativas, 9 cursos, 5 áreas e 78 vínculos**, com peso proposto de 1 por vínculo. Engenharia Civil e Mecânica formam uma única opção, assim como Enfermagem e Fisioterapia. Cada grupo recebe apenas um vínculo por afirmativa, sem duplicar a pontuação. As abas `Tabela_Area` e `Tabela_Cursos` usam os mesmos 9 cursos já agrupados; o validador confere os nomes diretamente, sem separar e reagrupar os pares. Os textos originais são preservados, inclusive possíveis erros de digitação.

Valide sem precisar de banco (comandos a partir da raiz):

```bash
cd backend
uv run --frozen python -m app.catalog validate
# Opcional: regenerar o relatório de revisão versionado.
uv run --frozen python -m app.catalog validate --report catalog/quiz-final.json
```

O catálogo é instalado automaticamente por `alembic upgrade head`. Não há comando de importação nem etapa de publicação. Alterar a planilha não modifica o banco instalado; a aplicação utiliza o catálogo fixo carregado pela migração.

O validador exige o modelo das duas abas e rejeita fórmulas, números ou frases duplicados, cursos desconhecidos, vínculos repetidos e conteúdo incompleto. `--file /caminho/planilha.xlsx` permite conferir uma planilha com a mesma estrutura. As listas de espaços são referências por área; as pendências institucionais continuam descritas no relatório JSON.

## Cálculo de afinidade

`calculate_scores`, em `backend/app/scoring.py`, recebe um `ScoringCatalog` com todas as áreas, cursos, afirmativas e pesos do quiz único e exatamente 25 UUIDs de afirmativas únicas. O motor não acessa o banco.

O método `area_distinct_count_course_sum_v1` soma um ponto por área distinta em cada afirmativa e soma os pesos positivos dos vínculos para cada curso. Todas as áreas com a maior pontuação vencem; dentro de cada área vencedora, todos os cursos com a maior pontuação positiva são recomendados. Os pontos não são normalizados nem apresentados como percentuais.

O resultado contém pontuações/indicadores de todas as áreas e cursos, inclusive os com zero. A ordem dos identificadores é estável e não desempata resultados. Escolhas inválidas geram `InvalidSelectionError`; catálogo inconsistente ou método desconhecido gera `ScoringConfigurationError`, sem produzir resultado parcial.

Para executar somente os testes do cálculo, a partir da raiz:

```bash
uv run --project backend --frozen pytest backend/tests/test_scoring.py
```

Os testes cobrem limites, duplicatas, identificadores desconhecidos, vínculos inválidos, pesos, empates, ausência de normalização e o catálogo original de 74 afirmativas. O motor implementa a regra proposta; sua aprovação institucional continua pendente.

## API do participante

As rotas ficam sob a mesma origem do frontend, usando o proxy `/api`. O cadastro exige as migrações aplicadas e o aviso de uso dos dados configurado. A escola é informada em texto livre e salva em `school_name`. Todas as participações usam o mesmo catálogo fixo.

Configure `PRIVACY_NOTICE_VERSION` e `PRIVACY_NOTICE_TEXT` no `.env`. O exemplo fornecido é somente para desenvolvimento com dados fictícios; substitua-o pelo aviso institucional aprovado antes do uso real. Sem ambos, a consulta do quiz e novos cadastros retornam 503. A versão apresentada precisa ser enviada no cadastro; ela registra qual aviso foi exibido, sem representar consentimento por si só.

| Método e rota | Comportamento |
|---|---|
| `GET /api/quiz/current` | Quiz único, aviso e afirmativas ordenadas, sem vínculos ou pesos. |
| `POST /api/participations` | Cadastro validado, participação em rascunho e cookie temporário. |
| `POST /api/participations/lookup` | Reconhece o e-mail ou telefone e informa o estado da participação mais recente, sem iniciar sessão. |
| `POST /api/participations/resume` | Retoma a participação reconhecida pelos contatos e renova a sessão. |
| `GET /api/participations/me` | Identificador, estado e expiração da própria sessão, sem contatos. |
| `GET /api/participations/me/quiz` | Afirmativas do quiz único para a sessão autenticada, sem vínculos ou pesos. |
| `POST /api/participations/me/submit` | Valida 25 escolhas, calcula e grava escolhas/resultados na mesma transação. |
| `GET /api/participations/me/result` | Resultado persistido da própria participação, com todas as áreas/cursos, empates e eventual confirmação. |
| `POST /api/participations/me/feedback` | Registra concordância, curso escolhido e destino exibido; conclui a participação na mesma transação. |
| `POST /api/participations/me/end` | Revoga a credencial e remove o cookie; preserva o registro e as respostas. |

Todos os POSTs exigem o cabeçalho `X-Quiz-Request: 1`. A API recusa requisições com `Sec-Fetch-Site: cross-site` e não habilita CORS. Esse cabeçalho personalizado é a proteção de CSRF para a API de mesma origem; qualquer futura abertura de CORS precisa preservar essa proteção. Referência: [OWASP — cabeçalhos personalizados para APIs](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html#employing-custom-request-headers-for-ajaxapi).

Exemplo do corpo do cadastro:

```json
{
  "school_name": "Escola do participante",
  "full_name": "Aluno de teste",
  "phone": "+5511999999999",
  "email": "aluno@example.org",
  "privacy_notice_version": "development-v1"
}
```

O cadastro retorna 201 com metadados da participação. O cookie é `HttpOnly`, `SameSite=Strict`, sem `Domain`, válido por 60 minutos por padrão (`PARTICIPANT_SESSION_MINUTES`, de 1 a 240). Em produção (`APP_ENV=production`), usa `Secure` e o nome `__Host-iseday_participant`; em desenvolvimento, `iseday_participant`. O token aleatório só aparece no cookie; o banco guarda seu SHA-256. Envie o cookie nas chamadas seguintes e nunca use o UUID como credencial.

O envio recebe `{"statement_ids": ["uuid-1", "uuid-2", "..."]}`, com exatamente 25 UUIDs únicos do catálogo fixo. A API bloqueia a participação até o fim da transação. O mesmo conjunto de escolhas, em qualquer ordem, retorna o resultado salvo sem recalcular; outro conjunto após submissão retorna 409. Qualquer falha durante a gravação desfaz escolhas, pontuações e mudança de estado.

Repetir um cadastro idêntico com o cookie válido retorna 200 e a mesma participação. Dados diferentes na mesma sessão retornam 409 com orientação para retomar a participação existente. Sem sessão válida, contatos já utilizados retornam 409 até o aluno escolher retomar ou enviar `start_new: true` para criar outro teste. Uma sessão ausente, expirada ou revogada recebe 401; resultado ainda não submetido recebe 409. O encerramento é idempotente e retorna 204 mesmo sem sessão válida. A resposta de resultado inclui escolhas, pontuações e indicadores, sem contatos, pesos ou percentuais.

`POST /api/participations/lookup` recebe `email`, `phone` ou ambos e retorna `null` quando não há correspondência. Quando encontra uma participação, retorna apenas `status` e `matched_by` (quais dos contatos informados corresponderam), sem nomes, contatos salvos, identificadores ou resultados. A consulta não cria sessão. `POST /api/participations/resume` recebe os mesmos contatos, retoma a participação mais recente correspondente e retorna seus metadados com um novo cookie de sessão. A retomada funciona após expiração ou encerramento da sessão anterior, renova sua validade e invalida o token anterior dessa participação. As duas operações exigem `X-Quiz-Request: 1` e têm limites por IP em janelas independentes de 60 segundos, usando `PARTICIPANT_REGISTRATION_LIMIT`.

Para confirmar, envie apenas `{"agrees_with_result": true}`. O aluno não precisa escolher um curso: o encaminhamento indica o estande do curso sugerido pelo quiz, no ginásio. Em caso de empate, inclui os estandes de todos os cursos sugeridos.

Para discordar, envie `{"agrees_with_result": false}`. O encaminhamento indica o estande de Psicologia, também no ginásio. Valores como `"false"` e `1` não são aceitos como booleanos. Por compatibilidade com clientes anteriores, `chosen_course_id` continua opcional ao concordar e deve identificar um curso sugerido; ao discordar, deve estar ausente ou ser `null`. Destinos enviados no corpo são rejeitados.

Os novos encaminhamentos usam os estandes no ginásio, independentemente dos antigos espaços de vivência do catálogo. Confirmações anteriores mantêm os textos e os horários gravados.

O POST de feedback retorna 200 com `participation_id`, `status: "completed"`, `completed_at`, `agrees_with_result`, `chosen_course_id`, `destination`, `destination_instructions` e `answered_at`. Feedback e conclusão são gravados na mesma transação, sem mudar escolhas ou pontuações. A confirmação salva é definitiva. Repetir a mesma resposta e curso devolve a confirmação anterior, com os mesmos textos e horários. Uma resposta ou curso diferente após a conclusão retorna 409. Antes da submissão, qualquer tentativa de confirmar retorna 409.

`GET /api/participations/me/result` inclui `feedback: null` enquanto aguarda a confirmação e o objeto da confirmação após concluir. O destino é recuperado do registro salvo. A sessão continua válida até expirar ou chamar `/api/participations/me/end`, permitindo recuperar a orientação e repetir uma requisição que perdeu a resposta.

As respostas `/api/` usam `Cache-Control: no-store`; erros de validação omitem os valores enviados e falhas de banco retornam mensagem genérica. Há limites por IP em janelas de 60 segundos: `PARTICIPANT_REGISTRATION_LIMIT` (60) para cadastro e `PARTICIPANT_SUBMISSION_LIMIT` (120) para cada uma das operações de submissão e feedback, em janelas separadas. Cada operação também permite 30 tentativas por credencial por minuto. O excesso retorna 429 com `Retry-After`. O controle usa memória limitada por processo; implantações com múltiplos workers precisam de limite compartilhado no proxy. Configure proxies confiáveis no servidor antes de usar IPs encaminhados.

Os testes MySQL exercitam as rotas com banco real, rollback, isolamento de sessões, expiração, revogação, imutabilidade do catálogo, encaminhamentos para os estandes no ginásio, submissões e confirmações concorrentes. Execute-os com `./scripts/check-db.sh` ou com `TEST_DATABASE_URL` apontando para um banco descartável cujo nome termine em `_test`.

Antes da publicação, validar o conteúdo e a metodologia do quiz.

## Referências

- [Node.js](https://nodejs.org/en/download)
- [Vite](https://vite.dev/guide/)
- [Ambiente Python no FastAPI](https://fastapi.tiangolo.com/virtual-environments/)
- [Instalação do uv](https://docs.astral.sh/uv/getting-started/installation/)
- [Instalação do Docker](https://docs.docker.com/get-started/get-docker/)


## Administração e acesso aos resultados

Abra <http://localhost:5173/admin> ou use “Acesso administrativo” no rodapé do quiz. Sem sessão válida, a aplicação abre `/admin/login`. O administrador entra com e-mail e senha; não existe cadastro público nem conta ou senha padrão.

Após aplicar as migrações, crie a primeira conta em um terminal interativo, a partir da raiz:

```bash
(cd backend && uv run --frozen python -m app.admin create)
```

No Docker Compose:

```bash
docker compose exec -it api uv run --no-sync python -m app.admin create
```

O comando solicita e-mail, nome, senha e confirmação. A senha deve ter de 1 a 1024 caracteres, não aparece no terminal e é armazenada apenas como hash Argon2. Não passe senhas por argumentos, arquivos de configuração ou variáveis `VITE_*`. Uma conta com o mesmo e-mail, ignorando maiúsculas, é recusada. A migração inicial `0001_mysql` já cria as tabelas administrativas.

Para redefinir uma senha, use o comando abaixo, que solicita o e-mail e a nova senha e revoga todas as sessões anteriores da conta na mesma transação:

```bash
(cd backend && uv run --frozen python -m app.admin reset-password)
# Em containers:
docker compose exec -it api uv run --no-sync python -m app.admin reset-password
```

A sessão usa um cookie próprio, separado do participante: `iseday_admin` no desenvolvimento e `__Host-iseday_admin` em produção. O cookie é `HttpOnly`, `SameSite=Strict`, válido por oito horas por padrão, com `Secure` em produção. O banco guarda somente o SHA-256 do token opaco. `ADMIN_SESSION_MINUTES` ajusta a duração entre 1 e 1440 minutos; `ADMIN_LOGIN_LIMIT` limita as tentativas por minuto, tanto por IP quanto por conta (padrão: 10). Os limites são por processo, como os do participante; múltiplos workers exigem limitação compartilhada no proxy. IPs encaminhados arbitrariamente não contornam o limite.

Todas as rotas de consulta validam a conta ativa, expiração e revogação no servidor. Login e logout exigem `X-Quiz-Request: 1` e recusam requisições de outra origem, conforme a política de mesma origem da API. Respostas usam `Cache-Control: no-store`; contatos, senhas e tokens não são gravados em localStorage ou sessionStorage. Sair remove os dados da tela imediatamente, revoga a sessão e comunica o encerramento às outras abas. Se o encerramento falhar, a tela permite repetir antes de liberar outro login. Expiração ou resposta 401 exige novo acesso.

O painel apresenta:

- Participações paginadas, da mais recente para a mais antiga, com nome, escola, início, situação, todas as áreas vencedoras, cursos sugeridos e confirmação.
- Busca por nome e filtros por escola, situação, área vencedora, curso sugerido, concordância e período de início. As datas incluem os dias inicial e final no horário de Brasília. Os filtros ficam na URL e são preservados ao voltar do detalhe.
- Totais de iniciadas, em andamento, aguardando confirmação e concluídas, além de distribuição por escola, área e curso. A concordância considera apenas quem respondeu; ausência de confirmação não significa discordância. Empates contam a participação em cada categoria, sem duplicar os totais gerais.
- Detalhe com cadastro, datas, aviso apresentado, as 25 afirmativas selecionadas, pontuações completas, todos os empates, curso escolhido e encaminhamento efetivamente exibido. Rascunhos informam que ainda não há resultado.

As consultas usam os resultados persistidos, sem recalcular ou editar respostas. Login, logout, criação/redefinição de conta, listagem, resumo e abertura de detalhe geram auditoria com ator, ação, horário e eventual identificador da participação, sem copiar contatos ou senhas.

| Método e rota | Comportamento |
|---|---|
| `POST /api/admin/login` | Recebe `email` e `password`; cria a sessão e retorna identidade e validade. |
| `GET /api/admin/me` | Identidade e expiração da sessão administrativa. |
| `POST /api/admin/logout` | Revoga a sessão atual e remove o cookie; repetição é segura. |
| `GET /api/admin/options` | Nomes de escola salvos nas participações, áreas e cursos disponíveis para filtrar o histórico. |
| `GET /api/admin/participations` | Lista sem contatos, com `page` (padrão 1) e `page_size` (padrão 20, máximo 100). |
| `GET /api/admin/participations/{id}` | Cadastro, seleções, resultado e confirmação de uma participação. |
| `GET /api/admin/summary` | Contagens e distribuições do conjunto filtrado, independentemente da página. |

Listagem e resumo aceitam `q`, `school_name`, `status` (`draft`, `submitted`, `completed`), `area_id`, `course_id`, `agreement` (`yes`, `no`, `pending`), `date_from` e `date_to` (`AAAA-MM-DD`). O filtro de escola compara o nome salvo exatamente; as opções vêm dos nomes distintos já informados pelos participantes. Área e curso filtram apenas indicadores de vitória/sugestão. As consultas mantêm um retrato consistente do banco durante submissões concorrentes.

Os testes MySQL cobrem credenciais incorretas, conta inativa, cookies, expiração, revogação, troca de senha, isolamento do participante, limites, filtros, paginação, empates, rascunhos, histórico e auditoria. `npm --prefix frontend test` inclui os cenários administrativos de navegador, recuperação de erros e layout móvel. `npm --prefix frontend run test:live`, com `TEST_DATABASE_URL`, valida também cadastro → resultado → confirmação → login administrativo → consulta individual → logout contra a API e o banco reais, criando uma conta fictícia exclusivamente no esquema temporário do teste.

### Quiz único

O painel administrativo é dedicado às participações e à exportação. Não há cadastro de versões, editor de afirmativas/pesos/destinos nem operações de publicação e arquivamento. As antigas rotas `/api/admin/versions` e suas subrotas foram removidas.

### Exportação de resultados

No painel de participações, os botões **Exportar resultados filtrados (CSV)** e **Exportar resultados filtrados (XLSX)** baixam todas as participações correspondentes aos filtros aplicados, independentemente da página atual. Ambos incluem somente nome, escola, telefone, e-mail, áreas vencedoras, cursos sugeridos e confirmação. As áreas e os cursos usam os resultados salvos, incluem todos os empates e são separados por vírgulas. Para participações ainda sem resultado, essas duas colunas ficam vazias. A confirmação informa **Concordou**, **Discordou** ou **Sem resposta**, como no painel administrativo. O CSV usa UTF-8 com BOM e separador `;`; o XLSX preserva os telefones como texto e permite abrir diretamente no Excel.

A exportação exige autenticação, gera auditoria e neutraliza células que poderiam ser interpretadas como fórmulas. O limite é de 10.000 participações por arquivo; refine os filtros para conjuntos maiores.

| Método e rota | Comportamento |
|---|---|
| `GET /api/admin/export.csv` | Exporta o conjunto filtrado; aceita os mesmos filtros da consulta administrativa. |
| `GET /api/admin/export.xlsx` | Exporta os mesmos dados e filtros em uma planilha Excel. |

Os testes verificam a instalação do catálogo único, a imutabilidade do catálogo e dos resultados, concorrência, filtros, exportação e ausência das antigas rotas de versões. O teste com API e MySQL reais percorre cadastro, resultado agrupado, confirmação, consulta administrativa e exportação CSV e XLSX em um esquema descartável.
