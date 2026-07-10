# Operations Runbook

> MASTER_PLAN Task 10.8 · Sprint 10 (deploy/rollback/DR); kept current through
> Sprint 12 (A1 prod compose, A6 drift fix). Deploy, rollback, backup verification,
> and the most-likely failure modes for the V1 single-host stack. Companion docs:
> [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md) (release procedure),
> [`RAILWAY_DEPLOYMENT.md`](RAILWAY_DEPLOYMENT.md) (Railway PaaS deploy),
> [`PRODUCTION_VALIDATION.md`](PRODUCTION_VALIDATION.md) (post-deploy checks),
> [`LARGE_DOWNLOAD_STRESS_TEST.md`](LARGE_DOWNLOAD_STRESS_TEST.md) (capacity plan),
> [`SMOKE_TEST.md`](SMOKE_TEST.md) (launch smoke test), [`smoke-test.sh`](smoke-test.sh),
> [`migrate.sh`](migrate.sh), [`monitor-resources.sh`](monitor-resources.sh),
> [`restore-drill-report.md`](restore-drill-report.md), [`LOCAL_BOT_API.md`](LOCAL_BOT_API.md),
> [`VPS_DEPLOYMENT_CHANGES.md`](VPS_DEPLOYMENT_CHANGES.md) (what changed on the live VPS + why),
> [`../.env.production.example`](../.env.production.example),
> `MASTER_PLAN.md` §13 (config), §15 (observability), §14.8 (DR).

---

## 1. Topology (V1, single host)

| Process | Image | Purpose | Ports |
|---|---|---|---|
| `bot` | `Dockerfile.bot` | Telegram long-poll/webhook, handlers | — (webhook: `API_BIND_PORT`) |
| `worker` × `WORKER_COUNT` | `Dockerfile.worker` | Download jobs, broadcast, **cleanup** (partitions/retention/orphans) | — |
| `api` | `Dockerfile.api` | `/v1/health`, `/v1/ready`, `/v1/metrics` | `8080` (`API_BIND_PORT`) |
| `postgres` | `postgres:15` | Source of truth (partitioned) | `5432` |
| `redis` | `redis:7` | Cache + queue (AOF+RDB) | `6379` |
| `pgbouncer` | `edoburu/pgbouncer` | Transaction pooling (D-020) | `6432` |
| `uptime-kuma` | `louislam/uptime-kuma` | Probes `/v1/health` + `/v1/ready` | `3010→3001` |

Admin HTTP API (`/v1/admin/*`, Task 8.3) is **opt-in and disabled by default**
(D-051): the router is mounted only when `ADMIN_API_KEY` is set, otherwise those
paths 404. V1 ships with it off — leave `ADMIN_API_KEY` empty unless you need it.

---

## 2. Configuration

All env vars are in `MASTER_PLAN.md` §13.2 and `.env.example`. Required before boot:
`BOT_TOKEN`, `BOT_OWNER_TELEGRAM_ID`, `DB_*`, `REDIS_URL`. Observability:
`SENTRY_DSN` (empty → disabled), `SENTRY_ENVIRONMENT`, `TELEGRAM_ALERTS_CHAT_ID`
(empty → no Telegram alerts), `LOG_LEVEL`, `LOG_FORMAT=json`.

**Cross-process metrics:** to aggregate counters from all processes at the single
`/v1/metrics` endpoint, set prometheus-client's standard `PROMETHEUS_MULTIPROC_DIR`
to a **shared, writable, empty-at-boot** directory mounted into `bot`, `worker`, and
`api` (e.g. a tmpfs volume). When unset, `/v1/metrics` reports the api process's own
counters plus the live gauges (`queue_depth`, `active_workers`, `db_pool_in_use`,
`redis_connected`), which are always cross-process-accurate (read at scrape time).
The DB path goes through PgBouncer: set `DB_HOST=pgbouncer`, `DB_PORT=6432`.

---

## 3. Deploy

Production runs the full stack via `docker-compose.prod.yml` (Sprint 12 A1). App
config comes from `.env.production` (copy [`../.env.production.example`](../.env.production.example)
and fill it); infra secrets (`DB_*`) come from the shell env or `deploy/.env`. The
ordered, gated procedure is [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md); the
short form:

```bash
cd deploy
# 1. Bring up infrastructure first.
docker compose -f docker-compose.prod.yml up -d postgres redis pgbouncer uptime-kuma

# 2. Apply migrations (must reach the current head BEFORE the app boots).
#    Run from the repo root with the app env loaded.
alembic upgrade head           # current head: 202607050003

# 3. Build + start the app tier (bot, worker, api). Pin IMAGE_TAG for rollback.
IMAGE_TAG=<tag> docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps            # all services healthy?

#    (The self-hosted Bot API server is opt-in behind a profile — D-040:
#     docker compose --profile bot-api -f docker-compose.prod.yml up -d bot-api)

# 4. Smoke test (Task 12.3): scripted endpoint half, then the manual checklist.
./smoke-test.sh http://localhost:8080                   # → PASSED (3/3)
#    then complete SMOKE_TEST.md §2 (bot flows).
```

> Local/dev use `docker-compose.yml` and can run the processes directly
> (`python -m api.main` / `-m workers.main` / `-m bot.main`) against dev infra.

Point Uptime Kuma monitors at `/v1/health` (liveness) and `/v1/ready` (readiness).

---

## 4. Rollback

1. **App regression:** redeploy the previous image tag for `bot`/`worker`/`api`
   (they are stateless). No DB change needed if the schema head is unchanged.
2. **Migration regression:** migrations are additive (Hard Rule 8 — never rewrite a
   merged migration). To revert the last step: `alembic downgrade -1`, then redeploy
   the matching app image. Verify with `alembic current`. If a downgrade is unsafe
   (data loss), restore from backup (§5) instead.
3. **Confirm health:** `/v1/ready` returns 200 and Uptime Kuma is green before
   declaring the rollback complete.

---

## 5. Backup & restore verification

- Backups: PITR (WAL archive) + nightly base backup, 30-day off-site retention
  (`MASTER_PLAN.md` §14.8). Targets: **RPO ≤ 15 min, RTO ≤ 60 min**.
- **Verify monthly** with the restore drill — full procedure and the latest result in
  [`restore-drill-report.md`](restore-drill-report.md). A drill restores into a clean
  throwaway DB and compares migration head, row counts, and partition count to source.
- Redis is a cache: recoverable from Postgres + activity; quarterly RDB restore drill.

---

## 6. Common alerts & failure modes

Telegram alerts (§15.6) fire to `TELEGRAM_ALERTS_CHAT_ID` on `CRITICAL` log lines,
throttled to one per fingerprint per 5 min. Sentry captures exceptions tagged with
`component` (`bot`/`worker`/`api`), `correlation_id`, and `job_id`.

| # | Symptom / alert | Likely cause | First response |
|---|---|---|---|
| 1 | `/v1/ready` = 503, `redis_connected` = 0 | Redis down/unreachable | `docker compose restart redis`; check `REDIS_URL`, AOF disk space. Bot/worker recover automatically once Redis is back. |
| 2 | `/v1/ready` = 503, DB check failing | Postgres down, or PgBouncer misrouted | Check `tgbot_postgres`; verify the PgBouncer data path: `psql postgresql://USER:PW@pgbouncer:6432/telegram_bot -c 'select 1'`. `SHOW POOLS` for saturation (needs `ADMIN_USERS`/`STATS_USERS`). |
| 3 | `active_workers` = 0 / `queue_depth` climbing | All workers crashed or stuck | Check worker logs/Sentry (`component=worker`); restart `worker`. Heartbeats expire after `2×WORKER_HEARTBEAT_INTERVAL`; CleanupWorker sweeps orphaned `active_downloads`/`job_waiters` so new requests are not blocked. |
| 4 | Uploads failing / `errors_total{type="TelegramUploadError"}` rising | Telegram API / self-hosted Bot API issue, or >2 GB file | Verify `BOT_API_BASE_URL` server health (`LOCAL_BOT_API.md`); confirm `max_file_size` cap. Jobs retry up to `WORKER_MAX_RETRIES`, then `permanently_failed`. |
| 5 | DB disk filling / slow inserts | Partition rollover or retention not running | CleanupWorker pre-creates partitions and drops expired ones hourly; check its logs (`cleanup_partitions_*`, `cleanup_retention_*`). Manually ensure the next month's partition exists; confirm `*_retention_days` settings. |

### Quick diagnostics

```bash
curl -fsS localhost:8080/v1/ready | jq            # per-check readiness detail
curl -fsS localhost:8080/v1/metrics | grep -E '^(queue_depth|active_workers|redis_connected|db_pool_in_use)'
docker exec tgbot_postgres psql -U telegram_bot -d telegram_bot \
  -tAc "SELECT version_num FROM alembic_version;"  # confirm schema head
```

> **Forced-alert test (post-deploy):** emit a `CRITICAL` log from each process and
> confirm a throttled Telegram message arrives and Sentry receives the event tagged
> with the right `component`.
