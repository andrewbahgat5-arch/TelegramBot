# Backup / Restore Drill Report

> MASTER_PLAN Section 14.8 (Backups & Disaster Recovery) · Task 10.7.
> Append a new dated entry per drill. The PostgreSQL restore drill is **monthly**
> in production (Redis quarterly). Each entry records the exact commands so the
> drill is reproducible and the runbook ([`deploy/README.md`](README.md)) can point here.

PostgreSQL targets (Section 14.8): **RPO ≤ 15 min, RTO ≤ 60 min**, verified by a
restore into a clean throwaway database.

---

## Procedure (PostgreSQL)

Run from a host with Docker access to the stack (adjust DB/credentials per env):

```bash
SRC=telegram_bot
DST=telegram_bot_restore

# 1. Take a logical backup (custom format → parallelizable, selective restore).
docker exec tgbot_postgres pg_dump -U telegram_bot -d "$SRC" -Fc -f /tmp/backup.dump

# 2. Create a clean throwaway database.
docker exec tgbot_postgres dropdb  -U telegram_bot --if-exists "$DST"
docker exec tgbot_postgres createdb -U telegram_bot "$DST"

# 3. Restore into it.
docker exec tgbot_postgres pg_restore -U telegram_bot -d "$DST" /tmp/backup.dump

# 4. Verify (compare to source): migration head, row counts, partition count, sample read.
docker exec tgbot_postgres psql -U telegram_bot -d "$DST" -tAc \
  "SELECT version_num FROM alembic_version;"

# 5. Tear down the throwaway DB + dump.
docker exec tgbot_postgres dropdb -U telegram_bot --if-exists "$DST"
docker exec tgbot_postgres rm -f /tmp/backup.dump
```

> **Production note:** the dev drill uses `pg_dump`/`pg_restore` (logical). Production
> recovery is **PITR**: restore the latest nightly base backup, then replay WAL to the
> target time (Section 14.8 step 2). The integrity checks below apply to both; a
> production drill additionally restores into fresh compute + storage and runs the
> Section 14.8 smoke test (`/start`, one cached URL, one fresh URL).

---

## Drill Log

### 2026-06-25 — Drill #1 (Sprint 10, dev stack)

| Field | Value |
|---|---|
| Operator | Sprint 10 automation (Claude) |
| Stack | `deploy/docker-compose.yml` (postgres:15, `tgbot_postgres`) |
| Source DB | `telegram_bot` |
| Throwaway DB | `telegram_bot_restore` (created, restored, dropped) |
| Dump | custom format, 251 KB |
| Migration head | source `202606240001` == restore `202606240001` ✅ |
| Row-count parity | settings 31=31 · users 4=4 · advertisements 8=8 · media_metadata 38=38 · cached_files 60=60 ✅ |
| Partitions (`pg_inherits`) | 260 == 260 ✅ |
| Sample query (restore) | `SELECT key,value FROM settings WHERE key IN ('free_daily_limit','ads_enabled')` → `ads_enabled=true`, `free_daily_limit=10` ✅ |
| RTO observed | < 1 min (dev, 251 KB dump) — well within the 60 min target |
| Result | **PASS** — restore produced a complete, queryable, schema-faithful database. |

**Conclusion:** the logical backup → restore path is sound on the current schema
(`202606240001`), including all monthly partitions. No restore gaps found. Next
production drill: 30 days post-launch (Task 12.6), then monthly.
