# Manual Test Plan — Deferred Backlog (Tasks 8.3, 9.5.9, 9.5.10)

> **Scope:** Owner verification of the 2026-06-25 deferred-backlog session:
> - **8.3** — HTTP admin API (`/v1/admin/*`, `ADMIN_API_KEY`-gated).
> - **9.5.9** — `ad_events` per-event analytics (recorded off the hot path).
> - **9.5.10** — ad/broadcast scheduling (`scheduled_at` + due-poller).
>
> **Status of the work:** all three are `[~]` Under Review (code-complete, all gates green,
> nothing committed). This plan is what to run to verify before sign-off.
>
> **Paths**
> - Worktree: `J:\TelegramProjectNewCustomer\TelegramBot\.claude\worktrees\happy-bose-71ed46`
> - venv tools: `J:\TelegramProjectNewCustomer\TelegramBot\.venv\Scripts\`
>
> ⚠️ **Never paste secrets** (bot token, DB password, Sentry DSN, your real `ADMIN_API_KEY`)
> into a report. Only exit codes / counts / yes-no behavior are needed.

---

## 0. Prerequisites

1. Docker Desktop running; stack up and healthy: `tgbot_postgres`, `tgbot_redis`, `tgbot_pgbouncer`.
   ```powershell
   docker ps --format "table {{.Names}}\t{{.Status}}"
   ```
2. A working `.env` in the worktree (the one used for live testing) — **plus one new line** for the
   8.3 test only: `ADMIN_API_KEY=<pick-any-secret>`. The bot and worker do not need it.
3. DB migrated to head (idempotent):
   ```powershell
   cd J:\TelegramProjectNewCustomer\TelegramBot\.claude\worktrees\happy-bose-71ed46
   $V = "J:\TelegramProjectNewCustomer\TelegramBot\.venv\Scripts"
   & "$V\alembic.exe" upgrade head    # → 202606250002 (head)
   ```

---

> **⚠️ Before running the gate suite:** stop any `python -m workers.main` (worker) process.
> A live worker drains the shared Redis queue (`REDIS_QUEUE_DB`) and will steal a few jobs
> mid-test, making `test_concurrent_dequeue_no_duplicates` fail with e.g. `997 == 1000`.
> That is environmental, not a bug — the suite is 531/531 with no worker running.

## 1. Automated gate suite (no Telegram, ~2 min)

```powershell
cd J:\TelegramProjectNewCustomer\TelegramBot\.claude\worktrees\happy-bose-71ed46
$V = "J:\TelegramProjectNewCustomer\TelegramBot\.venv\Scripts"

& "$V\ruff.exe" check .
& "$V\ruff.exe" format --check .
& "$V\lint-imports.exe"
& "$V\mypy.exe" .
& "$V\bandit.exe" -r . -c pyproject.toml
& "$V\pytest.exe" -q
```

**Expected:**

| Gate | Expected |
|---|---|
| ruff check | `All checks passed!` |
| ruff format --check | `226 files already formatted` |
| lint-imports | `Contracts: 7 kept, 0 broken.` |
| mypy | `Success: no issues found in 226 source files` |
| bandit | `Low: 0  Medium: 0  High: 0` |
| pytest | `531 passed` |

**Optional — migration reverses cleanly:**
```powershell
& "$V\alembic.exe" downgrade -2; & "$V\alembic.exe" current   # → 202606240001
& "$V\alembic.exe" upgrade head;  & "$V\alembic.exe" current   # → 202606250002 (head)
```

---

## 2. Task 8.3 — HTTP admin API

Start the API process in its own terminal (from the worktree). Replace `<TID>` with a real
Telegram user id that has used the bot. Use a **throwaway** id for the ban step.

### 2a. Key UNSET → surface hidden (404), health still public
```powershell
$env:ADMIN_API_KEY=""
python -m api.main
```
Another terminal:
```powershell
curl.exe -i http://localhost:8080/v1/health         # expect 200 {"status":"ok"}
curl.exe -i http://localhost:8080/v1/admin/stats     # expect 404  ← hidden when disabled
```
Stop the process (Ctrl-C).

### 2b. Key SET → auth + endpoints
```powershell
$env:ADMIN_API_KEY="testkey123"
python -m api.main
```
Another terminal:
```powershell
# --- Auth ---
curl.exe -i  http://localhost:8080/v1/admin/stats                        # 401 (no header)
curl.exe -i -H "X-API-Key: wrong" http://localhost:8080/v1/admin/stats   # 401
curl.exe -s -H "X-API-Key: testkey123" http://localhost:8080/v1/admin/stats   # 200 JSON

# --- Reads ---
curl.exe -s -H "X-API-Key: testkey123" "http://localhost:8080/v1/admin/users?limit=5"
curl.exe -s -H "X-API-Key: testkey123" "http://localhost:8080/v1/admin/users?telegram_id=<TID>"
curl.exe -s -H "X-API-Key: testkey123" "http://localhost:8080/v1/admin/users/<TID>"
curl.exe -s -H "X-API-Key: testkey123" "http://localhost:8080/v1/admin/jobs?limit=5"
curl.exe -s -H "X-API-Key: testkey123" "http://localhost:8080/v1/admin/queue"
curl.exe -s -H "X-API-Key: testkey123" "http://localhost:8080/v1/admin/errors?limit=5"
curl.exe -s -H "X-API-Key: testkey123" "http://localhost:8080/v1/admin/settings"

# --- Mutations (change the DB — see warning below) ---
curl.exe -i -X POST -H "X-API-Key: testkey123" -H "content-type: application/json" -d '{\"reason\":\"api test\"}' "http://localhost:8080/v1/admin/users/<TID>/ban"    # 200, is_banned=true
curl.exe -i -X POST -H "X-API-Key: testkey123" "http://localhost:8080/v1/admin/users/<TID>/unban"                                                                  # 200, is_banned=false
curl.exe -i -X PUT  -H "X-API-Key: testkey123" -H "content-type: application/json" -d '{\"value\":\"25\"}'         "http://localhost:8080/v1/admin/settings/free_daily_limit"   # 200
curl.exe -i -X PUT  -H "X-API-Key: testkey123" -H "content-type: application/json" -d '{\"value\":\"not-an-int\"}'  "http://localhost:8080/v1/admin/settings/free_daily_limit"   # 400
curl.exe -i -X PUT  -H "X-API-Key: testkey123" -H "content-type: application/json" -d '{\"value\":\"1\"}'           "http://localhost:8080/v1/admin/settings/made_up_key"        # 404

# --- Restore the setting changed above ---
curl.exe -X PUT -H "X-API-Key: testkey123" -H "content-type: application/json" -d '{\"value\":\"10\"}' "http://localhost:8080/v1/admin/settings/free_daily_limit"
```

> ⚠️ `/ban` and `PUT /settings` really change the DB. Use a throwaway `<TID>` for the ban,
> and run the restore line so `free_daily_limit` returns to `10`.
>
> **Windows PowerShell quoting:** PowerShell mangles `-d '{\"reason\":\"api test\"}'` when the
> JSON value contains a space, so the `/ban` body fails with a curl/422 error. Use
> `Invoke-RestMethod` instead for bodies with spaces:
> ```powershell
> Invoke-RestMethod -Uri "http://localhost:8080/v1/admin/users/<TID>/ban" -Method Post `
>   -Headers @{ "X-API-Key" = "testkey123" } -ContentType "application/json" `
>   -Body '{"reason":"api test"}'
> ```
> `curl.exe` with spaceless bodies (e.g. `PUT /settings`) works fine as written.
>
> **`/unban` behavior (D-054):** unban clears `ban_reason` (and `banned_at`) → an unbanned
> user shows `ban_reason: null`. If you unbanned users *before* this fix, their old reason
> persists until you unban them again or clear it:
> `UPDATE users SET ban_reason=NULL, banned_at=NULL WHERE is_banned=false;`

**Report:** the auth trio codes (404 / 401 / 200) and the four mutation codes (200 / 200 / 400 / 404).

---

## 3. Bot manual tests (9.5.9 + 9.5.10)

Start the **bot** and the **worker** (two terminals, from the worktree):
```powershell
python -m bot.main
python -m workers.main
```
Run `/ad_*` and `/broadcast` from your **Owner** account (non-owners are silently ignored).

DB peek (DB/user come from your compose env):
```powershell
docker exec -it tgbot_postgres psql -U $env:DB_USER -d $env:DB_NAME
```

### 3a. Task 9.5.9 — ad_events analytics
1. `/ad_create title=Test text=Check this out button_text=Open button_url=https://example.com`
2. `/ad_list` → note the new ad id. Ensure ads are on: `/ad_global on` (or `/settings` → `ads_enabled=true`).
3. Send a real download request and complete it → the ad appears **as a reply under** the delivered
   file. Tap **Open**.
4. Peek:
   ```sql
   SELECT event_type, count(*) FROM ad_events GROUP BY 1;
   SELECT event_type, advertisement_id, placement, button_id, created_at
     FROM ad_events ORDER BY created_at DESC LIMIT 5;
   ```
   **Expected:** an `impression` row for the post-download ad. (Ad buttons are **URL buttons** by
   design — they fire no callback, so clicks are not event-logged; impressions are. Counters on
   `advertisements` still track both.)
5. `/ad_stats <id>` → the `impressions` counter rose too. Delivery speed is unchanged (the
   `ad_events` write happens in the background, off the hot path).

**Report:** yes/no an `impression` row appeared; yes/no the ad showed under the file.

### 3b. Task 9.5.10 — scheduling

**Scheduled broadcast (the due-poller):**
1. Pick a time ~2 minutes out, UTC, ISO-8601 (e.g. `2026-06-26T14:32:00Z`).
2. `/broadcast Hello scheduled test --at 2026-06-26T14:32:00Z` → reply says "… **scheduled** … UTC".
3. Confirm it does **not** arrive immediately:
   ```sql
   SELECT id, status, scheduled_at FROM broadcasts ORDER BY id DESC LIMIT 1;   -- status=pending
   ```
4. After the time passes → within ~5s the worker delivers it and `status` becomes `completed`.
5. Bad input: `/broadcast hi --at not-a-time` → "Invalid `--at` time"; **nothing** queued.

**Scheduled ad (selection gate):**
1. `/ad_create title=Future text=coming soon scheduled_at=<a future ISO time>`
2. `/ad_global on`; do a download → the future-scheduled ad should **not** appear yet (an
   unscheduled ad still appears normally).
3. `/ad_edit <id> scheduled_at=none` → clears the schedule; the ad can now appear.
4. (Optional) `/ad_broadcast <id> --at <future ISO>` → queued now, delivered once due.

**Report:** yes/no the broadcast held until its time then sent; yes/no the future ad stayed
hidden until cleared.

> Note: broadcast scheduling latency is bounded by the worker's idle poll interval (a few
> seconds), so a scheduled send fires shortly *after* its time, never before.

---

## 4. What to send back

- **§1:** the `pytest` count (`531 passed`) + alembic head; flag any non-green gate.
- **§2:** the auth trio codes (404 / 401 / 200) and the four mutation codes (200 / 200 / 400 / 404).
- **§3a:** yes/no `impression` row appeared; yes/no ad shown under the file.
- **§3b:** yes/no broadcast held then sent; yes/no future ad hidden until cleared.
- Anything that behaved differently — paste the bot's reply text or the error (no secrets).

If it all checks out, that verifies **8.3 + 9.5.9 + 9.5.10**. Next step: Owner sign-off on
Sprints **9 + 9.5 + 10**, then Sprint 11 (testing framework, security, load/stress). The
F-1/F-2/F-3 roadmap items remain not-started.
