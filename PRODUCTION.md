# Execução em produção

O ambiente de produção é independente de `compose.yaml` e não precisa de Node.js ou Python no servidor. Precisa de Docker com Compose, disco persistente e, para acesso público, um domínio apontado para o servidor com as portas TCP 80 e 443 disponíveis. A escolha do provedor pode ser feita depois.

O Caddy entrega o build do React e encaminha `/api` para o FastAPI no mesmo domínio. Ele emite e renova os certificados e redireciona HTTP para HTTPS. A API e o PostgreSQL não publicam portas no host. Há um único processo da API, sem recarregamento automático; para escalar para vários processos/réplicas, implemente limites de requisições compartilhados.

## Configuração inicial

Na raiz do repositório:

```bash
cp .env.production.example .env.production
chmod 600 .env.production
openssl rand -hex 32
```

Edite `.env.production` antes de executar qualquer serviço:

- `SITE_ADDRESS`: domínio, por exemplo `quiz.sua-instituicao.edu.br`, sem protocolo, caminho ou porta. Não use os domínios de exemplo em produção.
- `POSTGRES_PASSWORD`: senha exclusiva gerada acima. Não reutilize a senha local.
- `DATABASE_URL`: `postgresql+psycopg://iseday:SENHA@db:5432/iseday_quiz`, usando a mesma senha e os mesmos usuário/banco de `POSTGRES_*`. Senhas com caracteres reservados exigem codificação de URL; uma senha hexadecimal evita isso.
- `PRIVACY_NOTICE_VERSION` e `PRIVACY_NOTICE_TEXT`: versão e texto do aviso institucional aprovado. Valores com `$` ou `#` devem ficar entre aspas simples no arquivo de ambiente para preservar o conteúdo literal.
- `APP_IMAGE_TAG`: identificador da publicação, por exemplo `release-2026-10-30`. Use uma tag diferente em cada publicação para preservar as imagens anteriores.

O Compose recusa valores obrigatórios vazios. `APP_ENV=production` é definido pelo próprio arquivo de produção, ativando cookies seguros e desabilitando `/api/docs` e `/api/openapi.json`. `.env.production` não é versionado nem incluído nas imagens. Variáveis exportadas no terminal prevalecem sobre o arquivo; evite executar com variáveis de desenvolvimento exportadas.

As variáveis `POSTGRES_*` inicializam somente um volume vazio. Alterá-las no arquivo não muda a senha nem renomeia um banco já existente; essas operações exigem manutenção no PostgreSQL e atualização coordenada de `DATABASE_URL`.

Nunca publique o conteúdo de `.env.production` nem a saída de `docker compose config` sem `--quiet`: ela pode conter credenciais.

## Primeira inicialização

```bash
make prod-up
make prod-admin
```

`prod-up` constrói as imagens, aguarda o banco ficar saudável, aplica `alembic upgrade head` em um container temporário e só então inicia a API. Se a migração falhar, a API nova não inicia. Depois que a API estiver saudável, o servidor web é iniciado. O comando aguarda os serviços, mas a emissão do certificado público ainda depende de DNS e acesso externo ao servidor.

`prod-admin` solicita nome, e-mail e senha em terminal interativo. Não existe administrador padrão. Para redefinir uma senha:

```bash
docker compose --env-file .env.production -f compose.production.yaml exec api /app/.venv/bin/python -m app.admin reset-password
```

Abra `https://SEU_DOMINIO/admin`. Crie uma versão do catálogo em **Versões e destinos**. Revise perguntas, pesos, destinos e instruções e publique a versão somente após validação institucional. Sem aviso configurado e versão publicada, o cadastro de alunos permanece indisponível. Migrações não publicam conteúdo nem criam usuários.

Verifique os endpoints no domínio publicado:

```bash
curl --fail https://SEU_DOMINIO/api/health
curl --fail https://SEU_DOMINIO/api/health/ready
```

O segundo endpoint consulta o banco. Use-o no monitor de disponibilidade do provedor. Valide também cadastro → 25 escolhas → resultado → confirmação → encerramento e login/consulta administrativa.

## Operação e atualizações

```bash
make prod-logs
make prod-down
make prod-up
```

O nome do projeto é `iseday-quiz-production`; seus volumes e rede são distintos dos de desenvolvimento. `prod-down` preserva os volumes do PostgreSQL e do Caddy (certificados e CA local). Não execute `down --volumes` no ambiente real. Reiniciar um container não apaga o banco. Uma falha do disco ainda exige restauração de backup.

Para atualizar, faça backup, revise as migrações, obtenha o código da versão desejada, escolha uma nova `APP_IMAGE_TAG` e construa as imagens antes da janela de manutenção:

```bash
make prod-build
docker compose --env-file .env.production -f compose.production.yaml stop frontend api
make prod-up
```

Há uma janela de indisponibilidade. A parada explícita impede que uma API antiga continue atendendo durante a migração. Se a migração falhar, investigue os logs antes de reabrir o tráfego. Mantenha o código e as imagens da publicação anterior. Voltar uma imagem exige compatibilidade com o esquema atual; não execute downgrade destrutivo como procedimento automático de recuperação.

O proxy ignora cabeçalhos `X-Forwarded-*` fornecidos pelo cliente e gera os cabeçalhos encaminhados a partir da conexão recebida. A API confia nesses cabeçalhos porque está restrita à rede Docker interna. Não publique a porta 8000 mantendo `--forwarded-allow-ips=*`. Se acrescentar CDN, balanceador ou outro proxy antes do Caddy, configure explicitamente os proxies confiáveis para preservar o IP real. Revise os limites por IP para o público do evento, pois dispositivos da mesma rede podem compartilhar um IP público.

Os logs Docker têm rotação e a API não grava logs de acesso com parâmetros de consulta. Monitore também espaço em disco, disponibilidade, falhas de publicação e conclusão dos backups.

## Backup e restauração

Crie um backup lógico antes de cada atualização e periodicamente durante a operação:

```bash
mkdir -p backups
chmod 700 backups
docker compose --env-file .env.production -f compose.production.yaml exec -T db sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' > backups/quiz.dump
```

Use um nome diferente para cada backup e confira se o comando terminou com sucesso. A pasta `backups/` é ignorada pelo Git. Os arquivos contêm dados pessoais: restrinja o acesso e mantenha uma cópia protegida fora do servidor. Backup no mesmo disco não protege contra perda do servidor. O volume `caddy_data` também deve ser preservado; no ensaio local, ele contém a CA que assina os certificados.

Teste a restauração em um banco separado, nunca por cima do banco ativo. Por exemplo, no mesmo servidor PostgreSQL, crie uma base de verificação com outro nome:

```bash
docker compose --env-file .env.production -f compose.production.yaml exec -T db sh -c 'exec createdb -U "$POSTGRES_USER" iseday_restore_check'
docker compose --env-file .env.production -f compose.production.yaml exec -T db sh -c 'exec pg_restore -U "$POSTGRES_USER" -d iseday_restore_check --exit-on-error --single-transaction' < backups/quiz.dump
docker compose --env-file .env.production -f compose.production.yaml exec -T db sh -c 'exec psql -U "$POSTGRES_USER" -d iseday_restore_check -c "SELECT count(*) FROM participations"'
```

Depois da conferência, remova somente a base de verificação com `dropdb -U "$POSTGRES_USER" iseday_restore_check`, executado no container `db`. Para recuperação real, interrompa o tráfego e restaure em uma base nova; valide o conteúdo e ajuste as configurações antes de reabrir a aplicação.

## Ensaio local de produção

O ensaio automatizado usa as mesmas imagens e o mesmo Compose de produção. Exige Docker, Node.js 24/npm, OpenSSL, dependências do frontend instaladas e Chromium do Playwright:

```bash
npm --prefix frontend ci
cd frontend
npx playwright install chromium
cd ..
make check-production
```

Em Linux sem as bibliotecas necessárias ao Chromium, use `npx playwright install --with-deps chromium` para preparar o navegador e suas dependências.

O script cria um projeto exclusivo, senha aleatória, banco `iseday_production_test` e portas locais aleatórias. Não lê `.env.production`, não utiliza os volumes reais e não emite certificado público. O Caddy emite um certificado local para `localhost`; apenas o navegador desse teste ignora a confiança do certificado. O teste verifica o fluxo completo com banco real, cookies `Secure`/`HttpOnly`/`SameSite=Strict`, rotas diretas do React, cache de assets e respostas da API sem fallback HTML. Após reiniciar os containers, confere a persistência da participação concluída e da versão publicada; depois executa backup e restauração em outra base temporária. Os containers e volumes exclusivos do ensaio são removidos ao final.

Para um ensaio manual separado, preencha outro arquivo de ambiente com dados fictícios, use `SITE_ADDRESS=localhost`, `HTTP_BIND_ADDRESS=127.0.0.1`, `HTTP_PORT=8080` e `HTTPS_PORT=8443`, e atribua outro nome de projeto:

```bash
docker compose --project-name iseday-production-rehearsal --env-file /CAMINHO/ensaio.env -f compose.production.yaml up --build --detach --wait
```

Abra diretamente `https://localhost:8443`; o redirecionamento HTTP automático usa a porta HTTPS padrão, não a porta externa alternativa desse ensaio. O navegador exibirá aviso até que você confie na CA local do Caddy. Não use HTTP para contornar esse aviso: a sessão de produção depende de cookies seguros.

## Referências

- [Padrão de SPA com proxy de API no Caddy](https://caddyserver.com/docs/caddyfile/patterns#single-page-apps-spas)
- [HTTPS automático e certificados locais](https://caddyserver.com/docs/automatic-https)
- [Cabeçalhos encaminhados pelo Caddy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy#defaults)
- [Redes do Docker Compose](https://docs.docker.com/compose/how-tos/networking/)
