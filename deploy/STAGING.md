# Staging Environment — the default place to do work

Production serves real users. **Every** feature, bug fix, refactor, dependency bump,
config change and (where possible) migration is built and proven on staging first, and
production is only touched on the Owner's explicit, per-change approval. Confidence that
a change is correct is *not* authorisation.

Staging lives on the **same host** as production, in a separate directory, as a fully
independent stack.

| | Production | Staging |
|---|---|---|
| Directory | `/opt/telegram-bot` | `/opt/telegram-bot-staging` |
| Compose project | `telegram-bot-prod` | `telegram-bot-staging` |
| Compose file | `docker-compose.prod.yml` | `docker-compose.staging.yml` |
| Containers | `tgbot_*` | `tgbot_stg_*` |
| Image tag | `telegram-bot/*:v1` | `telegram-bot/*:staging` |
| App env file | `deploy/.env.production` | `deploy/.env.staging` |
| Database | `telegram_bot` | `telegram_bot_staging` (own volume) |
| API host port | 8080 | 8090 |
| Egress | WARP pool ×3 + HAProxy LB + residential proxy | its own single WARP (`socks5://warp:1080`) |
| Bot token | production bot | **separate staging bot** |

## The four separations that keep staging off production

Each one is load-bearing; losing any single one lets staging reach into production.

1. **Project name** — namespaces the network and named volumes, so staging has its own
   Postgres and Redis data.
2. **Container names** — `container_name` is explicit in both files, and an explicit name
   is *global to the docker daemon*. Without the `tgbot_stg_` prefix a staging container
   would collide with the running production one regardless of project name.
3. **Image tag** — production runs `:v1` (pinned by `IMAGE_TAG=v1` in production's
   `deploy/.env`). Building staging under that tag would **replace the images production
   runs**, taking effect on prod's next restart: a silent production deploy. Staging's
   `deploy/.env` sets `IMAGE_TAG=staging`.
4. **Host directory** — the compose binds are relative (`./secrets/…`, `./yt-dlp.conf`),
   so running from `/opt/telegram-bot-staging/deploy` gives staging its own files. This
   matters most for **cookies**: the yt-dlp wrapper writes rotated session cookies back
   into whatever jar it is handed, so a shared bind would let staging mutate — or
   expire — the cookies production depends on.

## Extra safety nets

- **D-032 boot guard.** Staging sets `DEPLOY_ENV=test` plus `PROD_BOT_TOKEN_FINGERPRINT`
  (the SHA-256 of production's token). If production's token is ever pasted into staging
  by mistake, the app **refuses to boot** instead of running a second bot against real
  users. `DEPLOY_ENV=test` has no other behavioural effect — `is_test` is not consulted
  anywhere else in app code — so staging still behaves exactly like production.
- **Own egress.** Staging has its own WARP tunnel and therefore its own egress IP
  (verified different from production's). A staging test burst cannot trip YouTube's
  per-IP bot-check against production — which has already happened once, on 2026-07-19.

## Not copied from production

`warp2`, `warp3`, `warp-lb` (staging gets one WARP, ~500 MB instead of ~1.5 GB) and
`uptime-kuma` (nothing to page about; frees port 3010). Because the LB is absent,
staging's `YTDLP_WARP_PROXY` points at `socks5://warp:1080` directly.

## Runbook

All commands from `/opt/telegram-bot-staging/deploy`.

```sh
# Apply code changes: upload changed files to /opt/telegram-bot-staging/<same path>
docker compose --profile bot-api -f docker-compose.staging.yml build bot worker api
docker compose -f docker-compose.staging.yml run --rm --no-deps --entrypoint "" bot \
    alembic upgrade head
docker compose --profile bot-api -f docker-compose.staging.yml up -d
docker logs tgbot_stg_bot --tail 50
```

Refresh staging's code from production's current state (keeps staging's env + secrets):

```sh
rsync -a --delete \
  --exclude 'deploy/.env' --exclude 'deploy/.env.staging' \
  --exclude 'deploy/.env.production' --exclude 'deploy/secrets/' \
  /opt/telegram-bot/ /opt/telegram-bot-staging/
```

## Installing the staging bot token

The token is a credential and must not travel through chat logs. Set it directly:

```sh
ssh root@<host>
nano /opt/telegram-bot-staging/deploy/.env.staging   # replace REPLACE_WITH_STAGING_BOT_TOKEN
cd /opt/telegram-bot-staging/deploy
docker compose --profile bot-api -f docker-compose.staging.yml up -d bot worker api
docker logs tgbot_stg_bot --tail 30                  # expect "Run polling for bot @<staging bot>"
```

## Promotion flow

1. Change staging → 2. build + migrate + run there → 3. test → 4. fix → 5. confirm stable
→ 6. **wait for the Owner's explicit approval** → 7. apply the identical change to
production via the normal `deploy/README.md` procedure (`capture-logs.sh` first).

## Errors & Logs dashboard (Grafana)

Grafana renders `error_logs` as the Errors and Logs views described in
`DESIGN_MONITORING.md`. Chosen over building a UI from scratch — and over Metabase,
which needs 1 GB+ for the JVM plus its own application database. Grafana ships a
built-in Postgres datasource, filterable table panels and cell data links, which is
exactly this feature, and it measures **61 MB** in practice.

**It is bound to 127.0.0.1 and must stay that way** — the tables show user URLs,
usernames and chat ids. Reach it over an SSH tunnel:

```sh
ssh -L 3001:localhost:3011 root@<host>     # staging
# then open http://localhost:3001  →  Dashboards → "Telegram Bot — Errors & Logs"
```

Credentials live in `/opt/telegram-bot-staging/deploy/.env` (`GRAFANA_ADMIN_USER` /
`GRAFANA_ADMIN_PASSWORD`), which is git-ignored.

**Grafana connects as `grafana_ro`, never as the app user.** That role has `SELECT` on
`error_logs` and nothing else — verified: `DELETE` and reading `users` are both denied.
A dashboard is a query tool and must not be able to write to production data. Create
the role with `deploy/grafana/readonly-role.sql`.

> Two gotchas when creating that role. The postgres image trusts connections on
> `localhost`, so `psql -h localhost` succeeds even with the wrong password — always
> verify with `-h postgres` (the real network path Grafana uses). And use an
> **alphanumeric** password: it passes through `.env`, compose interpolation, Grafana's
> `${VAR}` expansion and a SQL literal, each with its own quoting rules.

Dashboards and the datasource are **provisioned from files** in
`deploy/grafana/`, so they are version-controlled, survive a rebuild, and are identical
on staging and production.
