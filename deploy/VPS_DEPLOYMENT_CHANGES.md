# VPS Deployment — Changes & Fixes Log

> Single-host production deploy to a fresh Ubuntu 24.04 VPS (`213.136.89.247`, root,
> `/opt/telegram-bot`, Docker Compose). This file records **every problem hit, the
> root cause, and the fix**, plus which files changed. Companion: [`README.md`](README.md)
> (runbook). Secrets live only in `.env.production` / `deploy/.env` on the server — never here.

---

## 0. Deployment summary

- **Host:** Ubuntu 24.04.4 LTS, 4 vCPU / 7.8 GB RAM / 145 GB disk, Docker Engine 29.x + Compose v2.
- **Topology:** everything in Docker Compose (`docker-compose.prod.yml`). App tier (bot / worker / api)
  on top of postgres / redis / pgbouncer, plus: self-hosted **2 GB bot-api**, a **Cloudflare WARP pool**
  behind an **HAProxy** SOCKS LB, and a **bgutil PO Token** provider.
- **Bring-up:** `cd /opt/telegram-bot/deploy && docker compose --profile bot-api -f docker-compose.prod.yml up -d`.
- **Restart on reboot:** every service is `restart: unless-stopped` and Docker is `systemctl enable`d.

Final container set (13): `tgbot_bot`, `tgbot_worker`, `tgbot_api`, `tgbot_postgres`, `tgbot_redis`,
`tgbot_pgbouncer`, `tgbot_uptime_kuma`, `tgbot_bot_api`, `tgbot_warp`, `tgbot_warp2`, `tgbot_warp3`,
`tgbot_warp_lb`, `tgbot_bgutil_pot`.

---

## 1. Problem → root cause → fix

### P1 — YouTube: "Sign in to confirm you're not a bot"
- **Symptom:** every YouTube link failed; bot showed *"The service is busy right now."*
- **Root cause:** YouTube blocks **datacenter IPs**. yt-dlp on the VPS IP is challenged and
  `YtDlpProvider` maps it to a transient error → the generic busy message.
- **Fix (evolved to a free, robust stack — no paid proxy, no cookies):**
  1. **Cloudflare WARP** as a SOCKS proxy → a clean, non-datacenter egress IP. yt-dlp uses
     `--proxy socks5://warp-lb:1080`.
  2. **bgutil PO Token provider** (`brainicism/bgutil-ytdlp-pot-provider`) → generates the GVS
     PO token so media URLs are authorized (otherwise the download 403s). Wired via
     `--extractor-args youtubepot-bgutilhttp:base_url=http://bgutil-pot:4416` and the pip plugin
     `bgutil-ytdlp-pot-provider` baked into the bot/worker images.
  3. **Deno + EJS** → solves YouTube's JS signature / `n` challenge for the `web`/`tv` clients.
     Deno is baked into the images (`COPY --from=denoland/deno:bin`); yt-dlp fetches the solver
     via `--remote-components ejs:github`.
- **Result:** analysis up to **2160p**, real downloads (video-merge + mp3) work, **5/5 reliable**.
- **Files:** `yt-dlp.conf` (new, mounted at `/etc/yt-dlp.conf`), `Dockerfile.bot`, `Dockerfile.worker`,
  `docker-compose.prod.yml` (warp / bgutil-pot services).
- **Note on player clients:** forcing `player_client=web,tv` returns **0 formats** through WARP — use
  the DEFAULT client set. The android client works cookieless but is capped at 360p (SABR).

### P2 — Upload cap 50 MB → 2 GB
- **Change:** enabled the self-hosted Telegram Bot API server (compose `bot-api` profile,
  `TELEGRAM_API_ID`/`TELEGRAM_API_HASH` in `deploy/.env`, `BOT_API_BASE_URL=http://bot-api:8081`
  in `.env.production`). Switch procedure: stop app tier → `bot<TOKEN>/logOut` on the cloud API →
  recreate app tier against the local server (cloud locks for 10 min; local works immediately).

### P3 — Download jobs failing: `[Errno 13] Permission denied: /tmp/downloads/<job_id>`
- **Root cause:** the `downloads` volume mounts `/tmp/downloads` owned by **root**, but the worker
  runs as `appuser` (uid 10001) → it can't create the per-job folder. (Masked in early tests that
  wrote to world-writable `/tmp`.)
- **Fix:** `chown 10001` on the live volume **and** `RUN mkdir -p /tmp/downloads && chown appuser`
  in `Dockerfile.worker` so a fresh volume inherits correct ownership.

### P4 — Cookie file self-destructing (only relevant if cookies are used)
- **Root cause:** yt-dlp rewrites the cookie file after each run; 3 concurrent workers stripped the
  auth cookies within minutes → the "not a bot" check returned.
- **Fix:** a **wrapper** installed as `/usr/local/bin/yt-dlp` (real binary → `yt-dlp.real`, source
  [`ytdlp-wrapper.sh`](ytdlp-wrapper.sh)) gives each run a **private writable copy** of the
  **read-only** master cookie file, so the master never degrades and the read-only save-back never
  crashes. Cookies are currently **not required** (WARP+POT is enough); the master
  `secrets/cookies.txt` is empty so the wrapper is a pass-through. Drop a real `cookies.txt` there
  (chmod 444) only for **age-restricted** videos.

### P5 — Free proxies were useless (context)
- Tested the user's free-proxy list: **0 of 2000** could even reach YouTube over HTTPS. Free proxies
  are not a solution — WARP replaced them.

### P6 — Bot crash on every download: `redis ... invalid expire time in 'set' command`
- **Symptom:** friend's requests errored; **mp3 (and all) downloads hung** with no response.
- **Root cause:** `download_cooldown_seconds` was set to **0** (via `/admin`). Picking a quality →
  `RateLimitService.check_download` → `RedisCache.set(key, "1", ex=0)`, and Redis **rejects a
  0-second expiry** → the whole update throws → the download never enqueues.
- **Fix (code):**
  - `services/rate_limit_service.py` → only arm the cooldown when `cooldown > 0` (0 = no cooldown).
  - `infrastructure/redis/cache.py` → `RedisCache.set` treats `ttl <= 0` as "no expiry" (safety net
    so a 0/disabled TTL can never crash a caller again).
- **Verified:** `set(ttl=0)` no longer errors; mp3 download works end-to-end; 0 bot errors after restart.

### P7 — Downloads stuck "already being prepared" after a restart (stale locks)
- **Symptom:** a download processed for >1h, the bot restarted, and afterwards every
  retry of that file returned *"This is already being prepared"* and refused to start.
- **Root cause:** the queue is a reliable queue — `dequeue` moves a job from
  `queue:jobs` (sorted set) into the `queue:active` set, and the worker `ack`s (removes
  it) only *after* processing. A crash/restart **between dequeue and ack** strands the
  job in `queue:active` forever (nothing re-drives it), while its `active_downloads`
  row (the dedup gate, created by the bot) persists. The orphan sweep only deletes
  `active_downloads` whose job is **terminal**, but a stranded job stays non-terminal
  (its `PROCESSING` update was rolled back with the killed transaction, so it's still
  `QUEUED`) — so it was never swept, and `insert_if_absent` kept reporting a duplicate.
- **Fix (production-grade, robust to bot/worker/server restarts):**
  1. **Reliable-queue crash recovery at startup** — `QueueService.recover_inflight()`
     moves every `queue:active` member back to `queue:jobs`. It runs once in
     `workers/main.py` **before any worker starts dequeuing** (race-free), so stranded
     jobs are re-processed and **delivered from the durable `job_waiters` table**
     (at-least-once); on completion the `active_downloads` slot is released, and a job
     that can no longer succeed fails through to terminal and is swept.
  2. **Startup orphan sweep** — also runs `sweep_orphans()` at boot to drop
     `active_downloads`/`job_waiters` whose job is already terminal.
  3. **Periodic stalled-job backstop** — the CleanupWorker now also fails jobs stuck in
     `PROCESSING` past a generous ceiling (default 2 h, age-gated so a still-running
     download is never reaped), covering a hang that happens *without* a restart.
- **Verified on the live server:** the 4 real stranded jobs were re-driven at startup
  (`startup_crash_recovery requeued_inflight=4`), reprocessed, **completed and
  delivered**, and `active_downloads` dropped to 0 — retries are unblocked immediately.

### F1 — Feature: image downloads (all sites)
- **Ask:** support downloading images (Pinterest pins and any site), skip the
  format picker, and put the source link in the caption.
- **How it works:**
  - New `MediaFormat.IMAGE` / `Quality.IMAGE`. `extract_info` now passes
    `--ignore-no-formats-error` so an image-only source (no video/audio formats)
    still returns metadata, and `_best_image_url` picks the picture **generically** —
    a direct image *format*/URL (`.jpg/.png/.webp/.gif…`), else a `/originals/`
    thumbnail (Pinterest), else the largest thumbnail, else the top-level image URL.
    The full-res URL rides in the option's `provider_format_id`; `download()` fetches
    it directly (no `-f`/merge). For image pins the caption title uses the pin
    **description** (yt-dlp labels them "Pinterest video #<id>").
  - `normalize_formats` passes IMAGE options through; `file_sender` sends images with
    **`send_photo`** (inline preview) and `_extract_upload` reads `message.photo`.
  - The handler **auto-downloads images unconditionally** (`_is_single_image`) — no
    "Choose a format" step, regardless of the auto-download-small preference.
  - The delivered caption appends the **source link** under the title for images
    (`_delivery_caption_base`). No third-party "saved by" branding.
- **Verified live:** Pinterest image pin and a direct Wikimedia `.jpg` both analyze to
  a single IMAGE option, download, and carry `title + source URL` in the caption.

### Known / watch
- One transient worker `asyncpg ConnectionDoesNotExistError` appeared during the `WORKER_COUNT`
  restart; none since. Watch under sustained load (asyncpg + PgBouncer transaction pooling).
- Cloudflare WARP **free** tier is fine for personal/moderate load; heavy sustained traffic may be
  throttled — scale the WARP pool or move to a residential-proxy pool.

---

## 2. Scaling changes

- **WARP pool:** `warp`, `warp2`, `warp3` (each its own tunnel/egress IP + `warpdataN` volume) behind
  `warp-lb` (HAProxy TCP `leastconn`, [`haproxy-warp.cfg`](haproxy-warp.cfg)) exposing one endpoint
  `warp-lb:1080`. **To add capacity:** add a `warpN` service + a `server warpN warpN:1080 check`
  line in `haproxy-warp.cfg`.
- **Workers:** `WORKER_COUNT` raised **3 → 8** in `.env.production` (merges are stream-copy/remux, so
  downloads are I/O-bound, not CPU-bound).
- **Capacity reality:** great for hundreds→low-thousands of *daily* users; the shared Redis queue +
  global `file_id` cache absorb bursts. **~1000 truly-simultaneous unique downloads needs horizontal
  scale** (more worker hosts pulling the shared queue + a bigger WARP/proxy pool) — not one 4-vCPU box.

---

## 3. Files changed in this repo

| File | Change |
|---|---|
| `services/rate_limit_service.py` | Guard `if cooldown > 0` before arming the Redis cooldown (P6). |
| `infrastructure/redis/cache.py` | `set()` treats `ttl <= 0` as no-expiry (P6 safety net). |
| `infrastructure/redis/queue.py` · `services/queue_service.py` · `domain/protocols/queue.py` | `recover_inflight()` — reliable-queue crash recovery (P7). |
| `workers/main.py` | Run `recover_inflight()` + `sweep_orphans()` at startup before workers dequeue (P7). |
| `infrastructure/database/repositories/job.py` · `infrastructure/database/maintenance.py` · `domain/protocols/maintenance.py` | `fail_stalled_inflight()` / `reclaim_stalled_jobs()` — periodic stalled-`PROCESSING` backstop (P7). |
| `workers/cleanup_worker.py` | Periodic age-gated stalled-job reclaim before the orphan sweep (P7). |
| `domain/enums/media_format.py` · `domain/enums/quality.py` | Add `IMAGE` media kind + quality (F1). |
| `infrastructure/downloader/providers/ytdlp_provider.py` | `--ignore-no-formats-error`, generic `_best_image_url`, image download, description-as-title (F1). |
| `services/format_extraction.py` | Pass IMAGE options through normalization (F1). |
| `infrastructure/telegram/file_sender.py` | Deliver images via `send_photo`; read `message.photo` (F1). |
| `bot/handlers/download.py` | Auto-download images with no picker (`_is_single_image`, F1). |
| `services/download_service.py` | Append the source link to image captions (`_delivery_caption_base`, F1). |
| `deploy/Dockerfile.bot` | Bake in Deno (EJS) + `bgutil-ytdlp-pot-provider` plugin. |
| `deploy/Dockerfile.worker` | Bake in Deno, `/tmp/downloads` ownership fix, the yt-dlp cookie wrapper, POT plugin. |
| `deploy/docker-compose.prod.yml` | Add `warp`/`warp2`/`warp3` + `warp-lb` (HAProxy) + `bgutil-pot` services and their volumes; mount `yt-dlp.conf` + `secrets/cookies.txt` into bot/worker. |
| `deploy/yt-dlp.conf` | **New.** yt-dlp runtime config (WARP proxy + POT base_url + EJS). Mounted at `/etc/yt-dlp.conf`. |
| `deploy/haproxy-warp.cfg` | **New.** HAProxy SOCKS load-balancer config for the WARP pool. |
| `deploy/ytdlp-wrapper.sh` | **New.** yt-dlp wrapper for a per-run private cookie copy. |
| `deploy/VPS_DEPLOYMENT_CHANGES.md` | **New.** This document. |

## 4. Server-only config (NOT in repo — secrets)

Set in `.env.production` on the server (copied from `.env.production.example`):
`BOT_TOKEN`, `BOT_OWNER_TELEGRAM_ID`, `DEPLOY_ENV=production`, `DB_PASSWORD`,
`BOT_API_BASE_URL=http://bot-api:8081`, `WORKER_COUNT=8`.
Set in `deploy/.env` (compose interpolation): `DB_NAME`, `DB_USER`, `DB_PASSWORD`,
`TELEGRAM_API_ID`, `TELEGRAM_API_HASH`.
`deploy/secrets/cookies.txt` — empty by default (optional, for age-restricted YouTube; chmod 444).

---

## 5. Post-launch session (2026-07-11) — download fix, chooser redesign, progress + history UX

All items below were edited in the worktree, uploaded to the same path under
`/opt/telegram-bot`, then `build` + `up -d` for the affected image (`bot` = chooser /
handlers, `worker` = download + upload + progress). Each was verified live inside the
container with a real extraction/download before moving on.

### P8 — Downloads completely broken: `progress_cb` TypeError (regression)
- **Symptom:** every video **and** audio download failed; every job went to
  `job_permanently_failed`. Bot had been fine "until yesterday".
- **Root cause:** the live download-progress feature added a `progress_cb` keyword to
  `DownloaderProtocol.download`, the yt-dlp provider, and `DownloadService`, **but not to
  `DownloaderRegistry.download`** — and the registry is the concrete `DownloaderProtocol`
  the service actually calls. So every download raised
  `DownloaderRegistry.download() got an unexpected keyword argument 'progress_cb'`.
- **Fix:** add `*, progress_cb=None` to `DownloaderRegistry.download` and forward it to the
  selected provider. (`infrastructure/downloader/registry.py`)

### F2 — Chooser redesign: richer metadata + per-quality size in the description (not on buttons)
- **Goal:** match a competitor bot's denser info card; move each quality's size off the
  buttons and into the message body.
- **Changes:**
  - Provider `_curated_metadata` now also keeps `upload_date`, `comment_count`, `channel`,
    `channel_follower_count` (flows through the cache + DB to both chooser screens).
  - New chooser caption: title · duration · platform · `👁 views  👍 likes  💬 comments
    📅 date` · `👤 channel · N subscribers`, then a **Video/Audio formats block** listing
    every option as `• <quality> — mp4 · <size>`.
  - Quality buttons now show the quality/codec label **only** (no `(~size)` suffix).
  - i18n: `download.subscribers`.
- **Files:** `bot/handlers/download.py`, `bot/keyboards/quality_select.py`,
  `infrastructure/downloader/providers/ytdlp_provider.py`, `core/locales/{en,ar}.json`.

### P9 — Progress bar: wrong final size + long "stuck at 100%" gap before send
- **Symptom:** at 100% the size shown was e.g. `2.6 MB / 2.6 MB` (not the real file), then a
  long delay with no feedback before the video arrived.
- **Root cause:** (a) a merged video downloads the video stream then the audio stream as two
  **separate** 0→100 passes, so the trailing tiny audio stream's total overwrote the bar with
  a misleadingly small "100%"; (b) `NotificationService.notify_stage(UPLOADING/PROCESSING)` is
  a **no-op** (single-status-line UX), so the stale download bar stayed on screen during the
  ffmpeg merge **and** the (often long) upload to Telegram.
- **Fix:** the moment the file is ready, replace the bar with `⬆️ … 100% / <real size> /
  Uploading to Telegram…`; show `⚙️ Processing…` during audio transcode; and in the progress
  callback, suppress any stream far smaller than the largest seen (drops the tiny trailing
  audio frame). (`services/download_service.py`, `core/locales/{en,ar}.json`)

### F3 — History rows: drop emojis, use real numbers
- Number badges `1️⃣ 2️⃣ …` → plain `1.` `2.`; removed the time emoji (`🕐`) and the
  platform/source emoji (`▶️`). Platform name kept as plain text. (`bot/handlers/history.py`)

### P10 — History: unwanted YouTube link preview under the list
- **Symptom:** a large YouTube preview/player rendered beneath the history list.
- **Root cause:** the clickable row titles (item #8) are links, so Telegram auto-renders a
  web-page preview for the first one.
- **Fix:** `link_preview_options=LinkPreviewOptions(is_disabled=True)` on the history send +
  edit. Titles stay clickable; no preview. (`bot/handlers/history.py`)

### Note — live progress feature folded into this commit
The download-progress feature it depends on (`domain/protocols/downloader.py`,
`ytdlp_provider._run_with_progress`/`_parse_progress`, `download_service._download_progress_cb`
/`_render_progress`, and its tests) was already deployed but **uncommitted** before this
session; it is included in this commit.

### Windows/paramiko deploy gotchas hit this session (for next time)
- **Git Bash mangles `/opt/...` argv** into a Windows path (`C:/Program Files/Git/opt/...`)
  when calling the paramiko uploader → run the uploader from **PowerShell** instead.
- **Remote emoji output crashes local `print`** on Windows cp1252 → set
  `PYTHONIOENCODING=utf-8` before the SSH helper.
- **`docker exec … python -c "…"` with spaces/quotes** gets re-split by the paramiko exec
  wrapper → write a `.py` file, `docker cp` it into the container, run that.
- **Host `/tmp` ≠ container `/tmp`** → always `docker cp` the script into the target container.
- Pre-existing unrelated red test `tests/unit/test_enums.py::test_media_format_values` (stale
  since the `IMAGE` kind was added, F1) — left untouched.

### Files changed this session

| File | Change |
|---|---|
| `infrastructure/downloader/registry.py` | Forward `progress_cb` through `DownloaderRegistry.download` (P8). |
| `bot/handlers/download.py` | Rich chooser caption + per-quality size list in the description (F2). |
| `bot/keyboards/quality_select.py` | Quality buttons show the label only — size moved to the caption (F2). |
| `infrastructure/downloader/providers/ytdlp_provider.py` | `_curated_metadata` adds date/comments/channel/subscribers; live-progress `_run_with_progress`/`_parse_progress` (F2, progress feature). |
| `services/download_service.py` | Uploading/processing status with the real file size; suppress tiny trailing stream; `_download_progress_cb`/`_render_progress` (P9, progress feature). |
| `domain/protocols/downloader.py` | `progress_cb` on the `download` protocol (progress feature). |
| `bot/handlers/history.py` | Plain-number rows, no time/source emoji (F3); disable link preview (P10). |
| `core/locales/{en,ar}.json` | `download.subscribers`, `notification.uploading`, `notification.processing`. |
| `tests/unit/{test_download_handler,test_download_service,test_download_progress,test_keyboards,test_history_handler,_fakes}.py` | Tests for all of the above. |

---

## 6. Session (2026-07-18) — analysis observability, global error backstop, YouTube cookies disabled

### Log review findings (what triggered this session)
- `analyze_transient_failure` events carried only the error text — no platform/host — so
  "which site is failing?" was unanswerable from production logs.
- Every YouTube run warned 4×: *"The provided YouTube account cookies are no longer valid"*
  (YouTube rotated the Jul 13 export). Extraction still worked logged-out via bgutil POT +
  EJS; the dead cookies only added noise and account-flag risk.
- `i18n_key_missing: platform.generic` (admin panel, generic-platform downloads).
- No global aiogram error handler: an unexpected handler bug would strand the user on a
  frozen "Analyzing…" message with no reply.

### Code deployed (commit `1b851fc`, images `bot`/`worker` rebuilt + recreated)
| File | Change |
|---|---|
| `bot/handlers/download.py` | All analysis log events now carry `platform` + `url_host` + 12-char `url_hash` (never the full URL); catch-all guard replies `errors.unexpected` instead of stranding the user. |
| `bot/handlers/errors.py` (new) | Global errors backstop: logs `update_handling_failed` (traceback + update context), best-effort localized apology (callback alert / message reply). |
| `bot/main.py` | Errors router installed first. |
| `core/locales/{en,ar}.json` | + `errors.unexpected`, + `platform.generic`. |

### Server-only change — YouTube cookies DISABLED (2026-07-18)
- `/opt/telegram-bot/deploy/secrets/cookies.txt` **truncated to empty** (the ytdlp-wrapper's
  `[ -s ]` check then skips `--cookies` entirely). Backup kept beside it:
  `cookies.txt.invalid-20260718`.
- Verified post-deploy: `yt-dlp -F` (worker container, residential proxy) → **0 cookie
  warnings, 24 DASH formats** for the test video. YouTube runs logged-out; public videos
  work via bgutil POT + EJS. **Consequence:** age-restricted / login-gated videos fail until
  a fresh cookie export is uploaded (restore = upload new export to the same path + recreate
  bot/worker).

### Same-day follow-up (commit `01fb033`) — root cause of "same error" + fixes deployed
- **Root cause found:** YouTube serves a per-video *"Sign in to confirm you're not a bot"*
  wall to our (reputation-degraded) residential-proxy egress IP. Verified live: the same IP
  passes for some videos (dQw4w9WgXcQ → 27 formats) and is walled for others
  (2oPfC_Pwfu8, jNQXAC9IVRw, CtE81HqupwU); nightly yt-dlp (2026.7.14.dev0) and the
  tv/web/web_safari clients and the WARP pool ALL fail; the wall is embedded in the initial
  webpage response, so PO tokens cannot bypass it. **Real cure = rotate the proxy IP with
  the provider, or restore fresh cookies.**
- **Deployed mitigations** (bot+worker rebuilt/recreated 07:48 UTC; verified in-container:
  walled video → `VideoUnavailableError` + `ytdlp_bot_check_wall` log; good video → OK):
  - Extraction keeps stderr; the wall is classified → users now get the honest localized
    "this video needs extra verification — try a different one" instead of "busy, retry".
  - Every analysis failure is persisted to the `error_logs` table (user, error_type,
    correlation id, platform/host/hash) — first writer to that table; browse via
    `/v1/admin/errors` or SQL.
  - ≥5 failed analyses within 10 min fire ONE CRITICAL `analyze_failure_burst` through the
    existing CRITICAL→Telegram alert pipeline (`TELEGRAM_ALERTS_CHAT_ID` is set in prod).
