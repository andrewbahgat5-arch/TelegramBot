# Production Smoke Test — Launch Checklist

> MASTER_PLAN **Task 12.3** · Sprint 12. Run this **immediately after a production
> deploy** (and after every rollback) to confirm the stack serves real traffic
> before declaring the release healthy. Companion: [`smoke-test.sh`](smoke-test.sh)
> (automated endpoint half), [`README.md`](README.md) (runbook), [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md).

This is a **Phase B / Owner-run** procedure: it needs the live production stack and
a real Telegram client. The endpoint checks are scripted; the bot-flow checks are
manual by nature (they exercise Telegram end-to-end).

---

## 0. Preconditions

- [ ] Deploy completed; `docker compose -f deploy/docker-compose.prod.yml ps` shows
      `bot`, `worker`, `api`, `postgres`, `redis`, `pgbouncer` **healthy/up**.
- [ ] Migrations at head: `alembic current` → **202607050003** (or the then-current head).
- [ ] You have a normal (non-owner) Telegram test account **and** the Owner account.

---

## 1. Automated endpoint checks (scripted)

Run:

```bash
deploy/smoke-test.sh https://<api-host>:<port>     # or default localhost:8080
```

Expected: `SMOKE TEST PASSED (3/3 endpoint checks)` and exit code 0.

| # | Check | Expected | Result |
|---|---|---|---|
| 1 | `GET /v1/health` | `200`, `{"status":"ok"}` | ☐ |
| 2 | `GET /v1/ready` | `200`, `ready=true` (DB + Redis + queue + worker) | ☐ |
| 3 | `GET /v1/metrics` | `200`, live gauges present (`queue_depth`, `active_workers`, `db_pool_in_use`, `redis_connected`) | ☐ |

---

## 2. Manual bot-flow checks (Task 12.3)

Perform each from the **test account** unless noted. Record the outcome.

| # | Flow | Steps | Expected | Result |
|---|---|---|---|---|
| 1 | **`/start`** | Send `/start` | Welcome message in the account's locale; user row created | ☐ |
| 2 | **Fresh download** | Send a supported-platform URL **not** downloaded before; pick a format/quality | Job runs; file delivered; visible in `/history` | ☐ |
| 3 | **Cached download** | Re-send the **same** URL + same format | Near-instant delivery from cached `file_id` (no re-download); `queue_depth` does not spike | ☐ |
| 4 | **`/stats`** | Send `/stats` (Owner) / open admin panel Statistics | Totals + cohort counts render, no error | ☐ |
| 5 | **Ad** | With an active ad configured, trigger the delivery path | Ad shown per placement/frequency rules; click button works; impression/click increment | ☐ |
| 6 | **Ban / unban** | Owner bans the test account (id), then unbans | Banned account is blocked from downloading; unban restores access; Owner is never self-targetable | ☐ |

> Ad step (5) is a no-op if no active ad is configured — mark N/A and note it.

---

## 3. Post-check

- [ ] `GET /v1/ready` still `200` after the flows (no check flipped to 503).
- [ ] No unexpected `CRITICAL` log lines / Sentry events during the run
      (see [`README.md`](README.md) §6). One deliberate forced-alert test is fine.
- [ ] Record the run in the release entry (see [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md)).

**Sign-off:** date `__________`, operator `__________`, result **PASS / FAIL**.

If any check fails: do **not** declare the release healthy — consult
[`README.md`](README.md) §4 (Rollback) and §6 (Common failure modes).
