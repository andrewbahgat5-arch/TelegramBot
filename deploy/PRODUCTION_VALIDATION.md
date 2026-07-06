# Production Validation Checklist

> Run **after deploying** (Railway or any host) to confirm the whole system works
> end-to-end before opening it to real users. Broader than
> [`SMOKE_TEST.md`](SMOKE_TEST.md) (which is the quick launch smoke) — this walks
> every subsystem. Needs the live stack + a real Telegram client. Owner-run.
>
> Have ready: the **api public URL** (`$API`), a normal **test account**, the
> **Owner account**, and a **second fresh account** (for referral). Replace `<TID>`
> with a Telegram id. Record PASS/FAIL per row.

---

## 1. Bot startup

- [ ] All services show **Running/healthy** (Railway) or `docker compose ps` all up.
- [ ] **bot** logs show `bot_starting mode=polling` (or `mode=webhook`) with no traceback.
- [ ] **worker** logs show `cleanup_worker_started` and worker startup lines; no crash loop.
- [ ] **api** logs show `api_starting host=0.0.0.0 port=<PORT>`.
- [ ] `curl $API/v1/health` → `{"status":"ok"}` (200).
- [ ] `curl $API/v1/ready` → `ready:true` (200) — DB + Redis + at least one worker heartbeat.

## 2. Telegram webhook / transport

- **Long-polling (default):** send `/start`; a reply arrives within ~1–2 s ⇒ polling
  is connected. (No webhook to check.)
  - [ ] `/start` replies promptly.
- **Webhook (only if configured):**
  - [ ] `getWebhookInfo` shows your `BOT_WEBHOOK_URL`, `pending_update_count` low, no
        `last_error_message`.
  - [ ] A message triggers a request to `/webhook` (check bot logs) and a reply.

## 3. User registration

- [ ] First `/start` from the **test account** → welcome message in its locale.
- [ ] DB row created with sane defaults:
      `SELECT telegram_id, role, is_banned, daily_download_count FROM users WHERE telegram_id=<TID>;`
      → role `user`, not banned, count 0.
- [ ] Second `/start` reuses the row (no duplicate; `SELECT count(*) … WHERE telegram_id=<TID>` = 1).
- [ ] Language switch (🌐) persists and the next message renders in the new locale.

## 4. Download flow

- [ ] Send a supported-platform URL; the format/quality picker appears.
- [ ] Pick a format → job runs → file delivered; a `downloads` row is written and the
      item shows in `/history`.
- [ ] `SELECT status FROM jobs ORDER BY created_at DESC LIMIT 1;` → `completed`.
- [ ] Delivered file size respects `max_file_size` / the active upload cap (50 MB public
      API, or 2 GB with the self-hosted bot-api).

## 5. Queue

- [ ] While a download runs, `curl $API/v1/metrics | grep -E '^(queue_depth|active_workers)'`
      shows `active_workers` ≥ 1 and `queue_depth` rising then draining to 0.
- [ ] Submit several downloads quickly → they are processed (FIFO by priority), none stuck.
- [ ] After completion, `queue_depth` returns to 0 and no orphaned `active_downloads`
      remain (the cleanup worker sweeps stragglers).

## 6. Cache

- [ ] Re-send the **same** URL + format → near-instant delivery from the cached
      `file_id` (no re-download; `queue_depth` barely moves).
- [ ] `/v1/ready` `redis` check is `ok`; `redis_connected` gauge = 1.
- [ ] (Optional) A settings change via the admin panel takes effect immediately
      (settings cache invalidation) — see §7.

## 7. Admin panel (Owner)

- [ ] From the **Owner** account, open the panel → the **live main-menu dashboard**
      renders (member/active/queue metrics) with no error.
- [ ] **Statistics** screen shows totals + cohort counts.
- [ ] **Settings** → open a field, change it (e.g. `free_daily_limit`), Save → toast
      confirms; the new value is enforced on the next download (no restart).
- [ ] **Users** → List renders; open a user → the profile card renders; Ban then Unban
      a test id works (Owner is never self-targetable).
- [ ] **Moderation** → Check Status runs the sweep and reports active/blocked/deleted counts.
- [ ] **Downloads / System / Errors / Jobs** screens all render.

## 8. Referral (D-066)

- [ ] From account **A**, `/referral` → shows A's `?start=ref_<CODE>` link, invites, bonus.
- [ ] From a **fresh account B**, open A's link (`/start ref_<CODE>`) → both get the
      "+N bonus downloads" message.
- [ ] `SELECT telegram_id, referral_bonus_downloads FROM users WHERE telegram_id IN (<A>,<B>);`
      → both bonuses incremented by `referral_reward_downloads`.
- [ ] **Bonus is enforced:** with a low `free_daily_limit`, B can download up to
      `limit + bonus` in a day (full procedure in
      [`../DAILY_LIMIT_VERIFICATION.md`](../DAILY_LIMIT_VERIFICATION.md)).

## 9. Broadcast (Owner)

- [ ] Admin panel → **Broadcast** → choose an audience → send a test broadcast.
- [ ] The message is delivered to the test account (chunked fan-out); no worker crash.
- [ ] `SELECT status, expected_total FROM broadcasts ORDER BY created_at DESC LIMIT 1;`
      progresses to completion; failures are isolated (a blocked user doesn't fail the batch).

## 10. Database migrations

- [ ] `alembic current` (or the migrate.sh output in deploy logs) = **`202607050003`**
      (or the then-current head), single head.
- [ ] Core tables exist and are populated as expected (`users`, `jobs`, `downloads`,
      `referrals`, `message_templates`, `settings`), and seeded `settings` rows are present.
- [ ] `downloads` monthly partitions exist for the current window.

## 11. Error logging

- [ ] Application logs are **structured JSON** on stdout (Railway/host log viewer),
      carrying `correlation_id` on request-flow lines.
- [ ] Trigger a benign handled error (e.g. send an unsupported URL) → the user gets a
      friendly message **and** an `error_logs` row / log entry is written (not a crash).
- [ ] (If Sentry configured) the event appears in Sentry tagged `component`
      (`bot`/`worker`/`api`).
- [ ] (If `TELEGRAM_ALERTS_CHAT_ID` set) force a `CRITICAL` line from each process and
      confirm one throttled Telegram alert arrives (see [`README.md`](README.md) §6).

---

## Sign-off

All sections PASS ⇒ the deployment is validated for real traffic.

**Validated by:** `__________`  **date:** `__________`  **result:** **PASS / FAIL**

Any FAIL → do not open to users; consult [`README.md`](README.md) §4 (rollback) / §6
(failure modes). For large-file capacity, run
[`LARGE_DOWNLOAD_STRESS_TEST.md`](LARGE_DOWNLOAD_STRESS_TEST.md) next.
