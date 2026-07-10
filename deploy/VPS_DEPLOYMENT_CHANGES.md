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
