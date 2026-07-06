# Railway Deployment Checklist

> How to deploy this bot to [Railway](https://railway.app). The app is a
> **multi-process** system (bot + worker + api) on top of **PostgreSQL + Redis**,
> so on Railway it maps to **3 app services + 2 managed data services** in one
> project. Companion docs: [`README.md`](README.md) (runbook),
> [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md) (generic release procedure),
> [`PRODUCTION_VALIDATION.md`](PRODUCTION_VALIDATION.md) (post-deploy checks),
> [`../.env.production.example`](../.env.production.example) (the LOCKED env key set).
>
> This is a **checklist** — nothing here deploys automatically. D-032: never
> deploy without intent.

---

## 1. Topology on Railway

| Railway service | Source | Public? | Notes |
|---|---|---|---|
| **api** | `deploy/Dockerfile.api` | **Yes** (domain) | Serves `/v1/health`, `/v1/ready`, `/v1/metrics`. Binds Railway's `PORT` (supported in code). Railway health check → `/v1/health`. |
| **worker** | `deploy/Dockerfile.worker` | No | Runs `WORKER_COUNT` in-process workers + cleanup/maintenance loops. Ships ffmpeg + pinned yt-dlp. |
| **bot** | `deploy/Dockerfile.bot` | No | Telegram **long-polling** (recommended on Railway — no inbound port/domain needed). |
| **Postgres** | Railway plugin | (private) | Source of truth. |
| **Redis** | Railway plugin | (private) | Cache (DB 0) + queue (DB 1). |
| **bot-api** *(optional)* | `aiogram/telegram-bot-api` image | No | Self-hosted Telegram Bot API for the 2 GB upload cap (D-040). Only if you need files >50 MB. See [`LOCAL_BOT_API.md`](LOCAL_BOT_API.md). |

> There is **no PgBouncer** service on Railway (that's a single-host-compose concern).
> Point `DB_*` at Railway Postgres directly, and keep `DB_POOL_SIZE`/`DB_MAX_OVERFLOW`
> within the plan's connection limit (§7). Railway also offers a pooled connection
> string if you hit limits.

---

## 2. Required services (create these first)

- [ ] Create a Railway **project**.
- [ ] Add a **PostgreSQL** database (New → Database → PostgreSQL).
- [ ] Add a **Redis** database (New → Database → Redis).
- [ ] Create **3 empty services** from this repo (New → GitHub Repo → this repo),
      one each for **api**, **worker**, **bot**. (Or `railway up` three times.)
- [ ] For each app service, set **Settings → Build → Dockerfile Path** to the right
      file: `deploy/Dockerfile.api` / `deploy/Dockerfile.worker` / `deploy/Dockerfile.bot`.
      (Root directory stays the repo root so the whole tree is in the build context.)

---

## 3. Environment variables

The full, authoritative key set is [`../.env.production.example`](../.env.production.example)
(mirrors MASTER_PLAN §13.2). On Railway, set the **shared** values once as
project **Shared Variables** and reference them from each service, then add the
few service-specific ones.

### 3a. Wire the data services (Railway reference variables)

In **each** app service (api, worker, bot), map the app's discrete DB vars to the
Railway Postgres service, and Redis to the Railway Redis service. Prefer **private
networking** (no egress cost):

```
DB_HOST     = ${{Postgres.PGHOST}}
DB_PORT     = ${{Postgres.PGPORT}}
DB_NAME     = ${{Postgres.PGDATABASE}}
DB_USER     = ${{Postgres.PGUSER}}
DB_PASSWORD = ${{Postgres.PGPASSWORD}}
DB_SSL      = false          # private network; set true if you use a public/proxied host
REDIS_URL   = ${{Redis.REDIS_URL}}      # or ${{Redis.REDIS_PRIVATE_URL}} for private networking
```

> The app uses **one** Redis instance with two logical DBs (`REDIS_CACHE_DB=0`,
> `REDIS_QUEUE_DB=1`) — a single Railway Redis is enough.

### 3b. Application config (Shared Variables, non-secret)

```
DEPLOY_ENV=production
BOT_OWNER_TELEGRAM_ID=<your numeric Telegram id>
BOT_PARSE_MODE=HTML
DEFAULT_LOCALE=en
LOG_LEVEL=INFO
LOG_FORMAT=json
SENTRY_ENVIRONMENT=production
WORKER_COUNT=3
DOWNLOAD_TEMP_DIR=/tmp/downloads
# ... remaining tunables default sensibly (see .env.production.example)
```

- [ ] `DEPLOY_ENV=production`, `LOG_FORMAT=json` (Railway captures stdout as logs).
- [ ] `BOT_WEBHOOK_URL` **empty** (long-polling). Leave `BOT_API_BASE_URL` empty
      unless you run the optional self-hosted bot-api service.
- [ ] `PORT` — **do not set**; Railway injects it into the **api** service and the
      app binds it automatically. (`API_BIND_PORT` stays the local/compose fallback.)

### 3c. Secrets (mark as secret / do not commit)

- [ ] `BOT_TOKEN` — from @BotFather.
- [ ] `DB_PASSWORD` — via the reference variable above (already a secret).
- [ ] `SENTRY_DSN` — optional; empty disables Sentry (OQ-1).
- [ ] `TELEGRAM_ALERTS_CHAT_ID` — optional; empty disables Telegram CRITICAL alerts (OQ-5).
- [ ] `ADMIN_API_KEY` — leave **empty** (the HTTP admin API is off in V1; admin is in-bot).
- [ ] `BOT_WEBHOOK_SECRET` — only if you switch to webhook mode (see §6).

> Everything in §3 must be present for **all three** app services (they each build
> a `Settings`, which requires `BOT_TOKEN`, `BOT_OWNER_TELEGRAM_ID`, `DB_*`, `REDIS_URL`).

---

## 4. Database migrations (before the app serves traffic)

The app does **not** self-migrate. Run [`migrate.sh`](migrate.sh) once per release:

- [ ] On the **api** service: **Settings → Deploy → Pre-Deploy Command** =
      `sh deploy/migrate.sh` (runs `alembic upgrade head` with the service's DB env
      before the new container starts).
- [ ] Confirm after deploy: logs show `alembic current` = **`202607050003`** (or the
      then-current head). Alternatively run once manually: `railway run sh deploy/migrate.sh`.

---

## 5. Health check & domain

- [ ] **api** service → **Settings → Networking → Generate Domain** (public URL).
- [ ] **api** service → **Settings → Deploy → Health Check Path** = `/v1/health`
      (always 200 when the process is up — good for deploy gating). Use `/v1/ready`
      for deeper monitoring (503 until DB + Redis + a worker heartbeat are present).
- [ ] **worker** and **bot** services need **no** domain and **no** health check
      (they don't listen on a port).

---

## 6. Domain / webhook requirements

- **Default: long-polling (recommended).** The bot service dials out to Telegram;
  it needs **no** public domain, webhook URL, or inbound port. Leave `BOT_WEBHOOK_URL`
  empty. This is the simplest and fully-supported Railway path.
- **Webhook (optional, advanced).** Only if you specifically want webhooks: give the
  **bot** service a public domain, set `BOT_WEBHOOK_URL=https://<bot-domain>/webhook`
  and a strong `BOT_WEBHOOK_SECRET`. Note: the webhook server currently binds
  `API_BIND_PORT`, not Railway's `PORT` — you'd need to align that first, so
  **prefer long-polling** for the initial launch.

---

## 7. Resource sizing (esp. for large downloads)

- [ ] **Worker disk:** downloads land in `DOWNLOAD_TEMP_DIR` (`/tmp/downloads`).
      Railway container disk is **ephemeral and limited**. For large files, attach a
      **Railway Volume** to the worker mounted at `/tmp/downloads`, sized ≥ 2–3× the
      largest expected file × concurrent workers. See
      [`LARGE_DOWNLOAD_STRESS_TEST.md`](LARGE_DOWNLOAD_STRESS_TEST.md).
- [ ] **Worker memory:** transcoding/muxing is CPU/disk-bound, not whole-file-in-RAM,
      but size the worker plan with headroom; validate with `monitor-resources.sh`.
- [ ] **Postgres connections:** `WORKER_COUNT` × pool + api pool must stay under the
      Railway Postgres connection limit — tune `DB_POOL_SIZE`/`DB_MAX_OVERFLOW`.
- [ ] **Upload cap:** public Telegram Bot API = **50 MB**. For up to **2 GB**, deploy
      the optional `bot-api` service and set `BOT_API_BASE_URL` (D-040). Telegram's Bot
      API does **not** support 50 GB uploads — see the stress-test plan's ceiling note.

---

## 8. Deploy order (first launch)

1. [ ] Postgres + Redis provisioned and green.
2. [ ] All env vars set on all three app services (§3).
3. [ ] Deploy the **api** service (its pre-deploy runs migrations to head).
4. [ ] Deploy **worker**, then **bot**.
5. [ ] `curl https://<api-domain>/v1/health` → `{"status":"ok"}`; `/v1/ready` → `ready:true`.
6. [ ] Run [`smoke-test.sh`](smoke-test.sh) against the api domain, then the manual
       halves in [`SMOKE_TEST.md`](SMOKE_TEST.md) and [`PRODUCTION_VALIDATION.md`](PRODUCTION_VALIDATION.md).

> Services start independently on Railway (no compose `depends_on`). If a worker/bot
> boots before Postgres/Redis is reachable it will exit and Railway restarts it until
> the data services answer — expected, self-healing.

---

## 9. Rollback

Railway keeps previous deployments per service. To roll back: **Deployments →** pick
the last-good deployment **→ Redeploy** (or `railway rollback`). If a migration must
be reverted, follow [`README.md`](README.md) §4 (`alembic downgrade -1` or restore
from backup) before redeploying the matching image.
