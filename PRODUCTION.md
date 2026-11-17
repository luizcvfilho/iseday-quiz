# Execução em produção

O ambiente de produção é independente de `compose.yaml`. O servidor precisa de Docker com Compose v2 ou superior (BuildKit habilitado), disco persistente e acesso de saída ao GitHub, aos registros de imagens e aos repositórios de pacotes. Para acesso público, precisa também de um domínio apontado para o servidor com as portas TCP 80 e 443 disponíveis. Não é necessário instalar Git, Python, uv, Node.js, npm ou Make no servidor.

O `Dockerfile.production` baixa com `curl` o código de uma versão do repositório público e constrói duas imagens: API com Python 3.13 e frontend compilado com Node.js 24, servido pelo Caddy. As dependências são instaladas dentro da construção, usando `uv.lock` e `package-lock.json`. O download e a compilação não são repetidos a cada inicialização dos containers. O código do backend e do frontend vem da mesma versão.

O Caddy entrega o build do React e encaminha `/api` para o FastAPI no mesmo domínio. Ele emite e renova os certificados e redireciona HTTP para HTTPS. O Compose não publica portas da API nem do MySQL. Há um único processo da API, sem recarregamento automático; para escalar para vários processos/réplicas, implemente limites de requisições compartilhados.

## Configuração inicial

Crie uma pasta de implantação no servidor e coloque nela estes arquivos, fornecidos pela equipe de desenvolvimento:

- `Dockerfile.production`
- `compose.production.yaml`
- `.dockerignore`
- `.env.production.example`
- `PRODUCTION.md` (este guia)

As pastas `backend/` e `frontend/` não são necessárias nesse modo. Os próprios arquivos de implantação precisam estar disponíveis antes da construção: são eles que ensinam o Docker a baixar o restante. A equipe pode gerar esse pacote no checkout com `make package-production`, ou `./scripts/package-production.sh` (com `zip` disponível na máquina que gera o pacote), e entregar `dist/iseday-quiz-deploy.zip`. Extraia-o pelo gerenciador de arquivos ou com `unzip iseday-quiz-deploy.zip` dentro da pasta escolhida. O pacote contém apenas os arquivos listados, sem configurações privadas.

Nessa pasta:

```bash
cp .env.production.example .env.production
chmod 600 .env.production
```

Edite `.env.production` antes de executar qualquer serviço:

- `APP_REPOSITORY`: repositório público no formato `dono/nome`. O padrão é `luizcvfilho/iseday-quiz`. Não inclua URL nem token.
- `CODE_VERSION`: SHA completo de um commit publicado no GitHub, ou uma tag de release que não seja alterada. Esse valor seleciona o código baixado. Prefira o SHA para garantir a mesma fonte em todas as construções; evite branches e outras referências mutáveis, cujo conteúdo pode mudar ou permanecer no cache de construção.
- `SITE_ADDRESS`: domínio, por exemplo `quiz.sua-instituicao.edu.br`, sem protocolo, caminho ou porta. Não use os domínios de exemplo em produção.
- Preencha `DATABASE_URL` no formato `mysql+pymysql://USUARIO:SENHA@db:3306/iseday_quiz?charset=utf8mb4`. O host `db` é o serviço MySQL no Compose. Senhas com caracteres reservados exigem codificação de URL.
- Preencha `MYSQL_DATABASE`, `MYSQL_USER` e `MYSQL_PASSWORD` com o mesmo banco, usuário e senha da aplicação em `DATABASE_URL`. Use outra senha para `MYSQL_ROOT_PASSWORD`.
- `PRIVACY_NOTICE_VERSION` e `PRIVACY_NOTICE_TEXT`: versão e texto do aviso institucional aprovado. Valores com `$` ou `#` devem ficar entre aspas simples no arquivo de ambiente para preservar o conteúdo literal.
- `APP_IMAGE_TAG`: identificador das imagens construídas, por exemplo o mesmo SHA de `CODE_VERSION`. Use um valor diferente em cada publicação para preservar as imagens anteriores. Essa variável nomeia a imagem; quem seleciona o código é `CODE_VERSION`.

Gere duas senhas fortes e distintas com o gerenciador de senhas da instituição. Se o servidor já tiver OpenSSL, `openssl rand -hex 32` é uma opção para gerar cada senha. Não é necessário instalar essa ferramenta para executar a aplicação.

O Compose recusa configurações obrigatórias de execução vazias e a construção remota falha se `CODE_VERSION` estiver vazio. `APP_ENV=production` é definido pelo próprio arquivo de produção, ativando cookies seguros e desabilitando `/api/docs` e `/api/openapi.json`. `.env.production` não é versionado nem incluído nas imagens. O Compose lê esse arquivo e fornece a cada serviço as variáveis declaradas em `environment`; o arquivo não é copiado para dentro dos containers. Variáveis exportadas no terminal prevalecem sobre o arquivo; evite executar com variáveis de desenvolvimento exportadas.

`APP_REPOSITORY` e `CODE_VERSION` são parâmetros de construção. Credenciais do banco, domínio e aviso institucional são configurações de execução. Para aplicar mudanças nessas configurações, execute novamente o comando de inicialização; o Compose recria os serviços afetados. Isso não exige reconstruir as imagens. Um simples `restart` não atualiza as variáveis dos containers existentes.

As variáveis `MYSQL_*` inicializam somente um volume vazio. Alterá-las no arquivo não muda senhas nem renomeia um banco existente. Nunca publique o conteúdo de `.env.production` nem a saída de `docker compose config` sem `--quiet`: ela pode conter credenciais.

Se usar contas separadas, configure `MIGRATION_DATABASE_URL` com a conta de migração, apontando para o mesmo banco. A conta da API deve ter `SELECT`, `INSERT`, `UPDATE` e `DELETE` no banco do quiz e nenhuma permissão de DDL. Assim ela não pode executar `TRUNCATE`, operação que não aciona gatilhos de linha no MySQL. Mantenha ativa a conta que criou os gatilhos, pois eles são executados com as permissões dessa conta.

A revisão inicial `0001_mysql` instala o esquema e o catálogo em uma base nova. Se houver participações ou contas em um PostgreSQL antigo, preserve o banco e o backup originais: a migração do esquema não copia esses dados. Nesse caso, planeje e valide a transferência em uma base de ensaio antes de apontar a API para o MySQL. O volume MySQL do Compose é separado do volume antigo.

## Primeira inicialização

```bash
docker compose --env-file .env.production -f compose.production.yaml up --build --detach --wait
docker compose --env-file .env.production -f compose.production.yaml exec api /app/.venv/bin/python -m app.admin create
```

O primeiro comando baixa a versão escolhida, constrói as imagens, aguarda o MySQL ficar pronto e aplica `alembic upgrade head` antes de iniciar a API. Se a migração falhar, a API nova não inicia. O MySQL confirma operações de DDL separadamente, então uma primeira migração interrompida pode deixar tabelas sem a revisão registrada. Confira os logs e use uma base nova para repetir a instalação inicial se a anterior ainda não contém dados. Depois que a API estiver saudável, o servidor web é iniciado. O comando aguarda os serviços, mas a emissão do certificado público ainda depende de DNS e acesso externo ao servidor.

O segundo comando solicita e-mail, nome, senha e confirmação da senha em terminal interativo. Ele usa o Python do container da API. Não existe administrador padrão nem senha administrativa embutida na imagem ou no arquivo de ambiente. Repita o comando para criar outros administradores com e-mails diferentes. Para redefinir uma senha:

```bash
docker compose --env-file .env.production -f compose.production.yaml exec api /app/.venv/bin/python -m app.admin reset-password
```

Abra `https://SEU_DOMINIO/admin` para acompanhar as participações. O catálogo fixo de 74 afirmativas e 9 cursos é instalado automaticamente pelas migrações. O aviso institucional continua obrigatório. As migrações não criam usuários.

Verifique os endpoints no domínio publicado:

```bash
curl --fail https://SEU_DOMINIO/api/health
curl --fail https://SEU_DOMINIO/api/health/ready
```

O segundo endpoint consulta o banco. Use-o no monitor de disponibilidade do provedor. Valide também cadastro → 25 escolhas → resultado → confirmação → encerramento e login/consulta administrativa.

## Operação e atualizações

```bash
docker compose --env-file .env.production -f compose.production.yaml logs --follow
docker compose --env-file .env.production -f compose.production.yaml down
docker compose --env-file .env.production -f compose.production.yaml up --detach --wait
```

O nome do projeto é `iseday-quiz-production`; seus volumes e rede são distintos dos de desenvolvimento. `down` preserva o volume do MySQL do Compose e os volumes do Caddy (certificados e CA local). Administradores e participações ficam no banco e são preservados ao atualizar as imagens. Não execute `down --volumes` no ambiente real. Reiniciar um container não apaga o banco. Uma falha do disco ainda exige restauração de backup.

Para atualizar, faça backup, revise as migrações e altere `CODE_VERSION` e `APP_IMAGE_TAG` em `.env.production`. A equipe de desenvolvimento também deve fornecer os arquivos de implantação correspondentes à nova versão caso tenham mudado. Não é necessário clonar o repositório. Construa as imagens antes da janela de manutenção:

```bash
docker compose --env-file .env.production -f compose.production.yaml build
docker compose --env-file .env.production -f compose.production.yaml stop frontend api
docker compose --env-file .env.production -f compose.production.yaml up --detach --wait
```

Há uma janela de indisponibilidade. A parada explícita impede que uma API antiga continue atendendo durante a migração. Se a migração falhar, investigue os logs antes de reabrir o tráfego. Mantenha o código e as imagens da publicação anterior. Voltar uma imagem exige compatibilidade com o esquema atual; não execute downgrade destrutivo como procedimento automático de recuperação.

Quem tiver o checkout completo e GNU Make pode continuar usando os atalhos `make prod-build`, `make prod-up`, `make prod-down`, `make prod-logs` e `make prod-admin`. Eles usam a mesma configuração de implantação.

O proxy ignora cabeçalhos `X-Forwarded-*` fornecidos pelo cliente e gera os cabeçalhos encaminhados a partir da conexão recebida. A API confia nesses cabeçalhos porque não publica porta no host e recebe as conexões web do Caddy na rede Docker privada. Não publique a porta 8000 mantendo `--forwarded-allow-ips=*`. Se acrescentar CDN, balanceador ou outro proxy antes do Caddy, configure explicitamente os proxies confiáveis para preservar o IP real. Revise os limites por IP para o público do evento, pois dispositivos da mesma rede podem compartilhar um IP público.

Os logs Docker têm rotação e a API não grava logs de acesso com parâmetros de consulta. Monitore também espaço em disco, disponibilidade, falhas de publicação e conclusão dos backups.

## Backup e restauração

Crie um backup antes de cada atualização e periodicamente durante a operação.

```bash
mkdir -p backups
chmod 700 backups
umask 077
docker compose --env-file .env.production -f compose.production.yaml exec -T db sh -c 'MYSQL_PWD="$MYSQL_PASSWORD" exec mysqldump -u "$MYSQL_USER" --single-transaction --no-tablespaces --set-gtid-purged=OFF --triggers "$MYSQL_DATABASE"' > backups/quiz.sql
```

Use um nome diferente para cada backup e confira se o comando terminou com sucesso. A pasta `backups/` é ignorada pelo Git. Os arquivos contêm dados pessoais: restrinja o acesso e mantenha uma cópia protegida fora do servidor. Preserve também o volume `caddy_data`.

Use uma base separada para testar a restauração.

```bash
docker compose --env-file .env.production -f compose.production.yaml exec -T db sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -u root -e "CREATE DATABASE iseday_restore_check CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin"'
docker compose --env-file .env.production -f compose.production.yaml exec -T db sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -u root iseday_restore_check' < backups/quiz.sql
docker compose --env-file .env.production -f compose.production.yaml exec -T db sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -u root iseday_restore_check -e "SELECT COUNT(*) FROM participations; SHOW TRIGGERS"'
```

Em uma recuperação real, interrompa o tráfego, restaure em uma base nova e garanta que a conta que define os gatilhos existe e tem acesso à base restaurada. Valide uma submissão e uma confirmação nessa base antes de apontar a API para ela e reabrir o tráfego.

## Ensaio local de produção

O ensaio automatizado usa o mesmo Dockerfile e Compose de produção, com `SOURCE_MODE=local` para copiar o código do checkout e testar inclusive mudanças ainda não publicadas no GitHub. As etapas de instalação e execução são as mesmas; somente a origem do código muda. Esse ensaio é uma ferramenta da equipe de desenvolvimento e exige Docker, Node.js 24/npm, OpenSSL, dependências do frontend instaladas e Chromium do Playwright:

```bash
npm --prefix frontend ci
cd frontend
npx playwright install chromium
cd ..
make check-production
```

Em Linux sem as bibliotecas necessárias ao Chromium, use `npx playwright install --with-deps chromium` para preparar o navegador e suas dependências.

O script cria um projeto exclusivo, senha aleatória, banco `iseday_production_test` e portas locais aleatórias. Não lê `.env.production`, não utiliza os volumes reais e não emite certificado público. O Caddy emite um certificado local para `localhost`; apenas o navegador desse teste ignora a confiança do certificado. O teste verifica o fluxo completo com banco real, cookies `Secure`/`HttpOnly`/`SameSite=Strict`, rotas diretas do React, cache de assets e respostas da API sem fallback HTML. Após reiniciar os containers, confere a persistência da participação concluída e do catálogo fixo; depois executa backup e restauração em outra base temporária. Os containers e volumes exclusivos do ensaio são removidos ao final.

Para um ensaio manual separado do download público, preencha outro arquivo de ambiente com dados fictícios e um `CODE_VERSION` publicado, use `SITE_ADDRESS=localhost`, `HTTP_BIND_ADDRESS=127.0.0.1`, `HTTP_PORT=8080` e `HTTPS_PORT=8443`, e atribua outro nome de projeto:

```bash
docker compose --project-name iseday-production-rehearsal --env-file /CAMINHO/ensaio.env -f compose.production.yaml up --build --detach --wait
```

Abra diretamente `https://localhost:8443`; o redirecionamento HTTP automático usa a porta HTTPS padrão, não a porta externa alternativa desse ensaio. O navegador exibirá aviso até que você confie na CA local do Caddy. Não use HTTP para contornar esse aviso: a sessão de produção depende de cookies seguros.

Para testar manualmente o código local com esse mesmo comando, acrescente `SOURCE_MODE=local` ao arquivo de ensaio e execute a partir do checkout completo. A implantação entregue ao servidor usa o padrão `SOURCE_MODE=remote` e dispensa as pastas de código.

## Referências

- [Padrão de SPA com proxy de API no Caddy](https://caddyserver.com/docs/caddyfile/patterns#single-page-apps-spas)
- [HTTPS automático e certificados locais](https://caddyserver.com/docs/automatic-https)
- [Cabeçalhos encaminhados pelo Caddy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy#defaults)
- [Redes do Docker Compose](https://docs.docker.com/compose/how-tos/networking/)
