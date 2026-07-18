# AI Project Index

> **Read me first.** This is the single entry point for any AI (or human) starting work on
> this repository. It does **not** duplicate other docs — it tells you *what each file is*
> and *when to open it*, so you can orient in 2–3 minutes instead of reading everything.
>
> **Keep this in sync — this file is the single source of truth for any AI on this project.**
> It must ALWAYS reflect the latest project structure, documentation, workflows, and
> development/deployment guidelines. Whenever the **architecture, workflow, deployment
> process/topology, or documentation** changes — a markdown doc added/removed/repurposed, a
> major component moved or added, a new service/process, or a change to how the project is
> developed or deployed — update this index **in the same change** (and mirror workflow/
> deployment changes into the sections below). Do not let it drift.
>
> **Last updated:** 2026-07-18 · Covers the live `claude/happy-bose-71ed46` branch (production).

---

## Project Overview

**What it is.** A production-grade **Telegram SaaS download bot** (V1): a user sends a video/
audio link (YouTube and other sites), the bot analyzes it, shows a quality chooser, downloads
via a provider-abstracted engine, and delivers the file — with a job queue, a global `file_id`
cache (instant re-sends), per-user history, an in-bot admin panel, ads, broadcasts, referrals,
and statistics. Target scale: ~20k daily / 300k monthly users.

**Architecture.** Clean / hexagonal, multi-process:

```
domain/          pure business types + protocols (no I/O, no frameworks)
   ↑
services/        business logic (reusable, framework-free)  ← the heart of the app
   ↑
infrastructure/  I/O adapters: Postgres, Redis, Telegram transport, yt-dlp/ffmpeg
   ↑
bot/  api/  workers/   entry processes (aiogram bot, FastAPI, background workers)
core/            cross-cutting: config, i18n, logging, metrics, redis keys, urls
```

Three runnable processes share Postgres + Redis: **bot** (URL analysis, handlers, admin
panel), **worker** (download → transcode → upload + progress), **api** (readiness + admin HTTP).

**Main technologies.** Python 3.13 · aiogram 3 · FastAPI · SQLAlchemy 2 async · Alembic ·
PostgreSQL (via PgBouncer) · Redis (reliable queue + cache) · yt-dlp + ffmpeg · Docker Compose.
Production runs on a VPS with a self-hosted 2 GB Telegram Bot API, a Cloudflare WARP pool, and
a residential proxy used **only for YouTube** (per-platform egress routing).

---

## Development Workflow & Deployment Topology

> **Canonical workflow — assume this for all development and deployment unless explicitly
> changed.** When the workflow or topology changes, update this section (see the "keep in
> sync" mandate at the top).

**Workflow (always in this order):**

1. **Develop locally.** Make all code changes on the local development machine (the git
   worktree is the source of truth). Follow the layering + rules in *Important Rules* below.
2. **Test locally.** Run the suite locally before deploying — `pytest tests/unit` (fast), plus
   `tests/integration` / `tests/e2e` where relevant; type-check with `mypy`, lint with `ruff`.
   Record outcomes in `TEST_RESULTS.md`. Never deploy an untested change.
3. **Deploy to production.** Push the change, then roll it out to the production server(s):
   **run `sh deploy/capture-logs.sh` first** (recreating a container destroys its logs),
   upload the changed files to the same paths under `/opt/telegram-bot`, rebuild the affected
   image(s), and recreate. See `deploy/VPS_DEPLOYMENT_CHANGES.md` (host + Windows/paramiko
   procedure) and `deploy/README.md` (runbook). Bring-up:
   `cd /opt/telegram-bot/deploy && docker compose --profile bot-api -f docker-compose.prod.yml up -d`.

**Deployment topology:**

| Tier | Role |
|---|---|
| **Local machine** | Development environment — write + test changes here first. |
| **Production Server #1** | **Main Telegram Bot** — runs the app stack (bot/worker/api + Postgres/Redis/PgBouncer, WARP pool, residential-proxy egress) via Docker Compose at `/opt/telegram-bot`. |
| **Production Server #2** | **Telegram Bot API server** — the self-hosted Telegram Bot API (2 GB upload cap) the bot talks to via `BOT_API_BASE_URL`. See `deploy/LOCAL_BOT_API.md`. |

> **Current state note (2026-07-18):** as presently deployed, the self-hosted Bot API runs as
> the `tgbot_bot_api` container **within the Server #1 Compose stack** (single-VPS). Treat
> "Server #2" as the logical Bot API tier; when it is split onto a dedicated machine, record
> that host here and in `deploy/VPS_DEPLOYMENT_CHANGES.md`.

**Server-side logs** are structured JSON on stdout (captured by Docker, rotation-capped at
20 MB × 10 per app service). Review with `docker logs --tail N tgbot_bot` / `tgbot_worker` /
`tgbot_api` — grep/jq-searchable (e.g. `docker logs tgbot_bot 2>&1 | grep admin_event`).

---

## Documentation Index

Docs are grouped by role. Each entry: **Purpose · Read when · Related.** (Generated artifacts —
`graphify-out/**`, `.pytest_cache/README.md` — are not project docs; see graphify note below.)

### Canonical / source-of-truth (read these before designing anything)

**MASTER_PLAN.md**
- Purpose: The canonical architecture, sprint plan, target scale, and **locked decisions**
  (referenced everywhere as `D-0xx`). Supersedes all prior reference docs.
- Read when: Starting any non-trivial task, or when you need the authoritative "why".
- Related: `project_reference.md`, `PROJECT_PROGRESS.md`.

**project_reference.md**
- Purpose: Master *architecture* reference (component map, layering, data flow).
- Read when: You need a structural overview deeper than this index but broader than the code.
- Related: `MASTER_PLAN.md`, `database_reference.md`.

**database_reference.md**
- Purpose: Database source of truth — schema, tables, partitioning, indexing rationale.
- Read when: Touching models, migrations, queries, or repositories.
- Related: `infrastructure/database/`, `migrations/`, `project_reference.md`.

**README.md**
- Purpose: Short project intro + pointer to the MASTER_PLAN.
- Read when: First contact / high-level orientation.
- Related: `MASTER_PLAN.md`.

**PROJECT_PROGRESS.md**
- Purpose: **LIVE** implementation status per task/sprint. Must never drift from reality.
- Read when: Checking what's done vs pending; **update it whenever task status changes.**
- Related: `TEST_RESULTS.md`, `SECURITY_REPORT.md`, `PERFORMANCE_REPORT.md`.

**COMMANDS.md**
- Purpose: Every command / interactive control the bot exposes, by role, generated from live
  handlers.
- Read when: Adding/changing user-facing commands or verifying access rules.
- Related: `bot/handlers/`, `domain/enums/user_role.py`.

**CLAUDE.md**
- Purpose: Project rules for AI agents — primarily the **graphify** workflow (query the
  knowledge graph first; `graphify update .` after code changes).
- Read when: Always (it governs how to explore the codebase efficiently).
- Related: `graphify-out/`, `SKILL.md`.

### Append-only validation SSOTs

**TEST_RESULTS.md** — Purpose: append-only record of test runs/outcomes. · Read when: after
running the suite or before claiming something is verified. · Related: `TEST_PLAN.md`,
`PROJECT_PROGRESS.md`.

**SECURITY_REPORT.md** — Purpose: append-only security-validation log (MASTER_PLAN §14). · Read
when: doing anything auth/permission/injection-adjacent, or a security review. · Related:
`MASTER_PLAN.md` §14, `TEST_RESULTS.md`.

**PERFORMANCE_REPORT.md** — Purpose: append-only performance & load-test log. · Read when:
working on throughput, queue, DB load, or download/upload speed. · Related:
`deploy/LARGE_DOWNLOAD_STRESS_TEST.md`.

**TEST_PLAN.md** — Purpose: manual test plan for a deferred backlog (admin API, `ad_events`
analytics, etc.). · Read when: manually verifying those specific features. · Related:
`TEST_RESULTS.md`.

### Feature docs

**ADS_SCHEDULING.md** — Purpose: advertisement scheduling UX + behavior. · Read when: working on
ads timing/placement. · Related: `services/ad_service.py`, `DESIGN_9.6_unified_audience_wizard.md`.

**ADS_MANUAL_TEST.md** — Purpose: end-to-end human test script for every ads feature. · Read
when: manually validating ads. · Related: `ADS_SCHEDULING.md`, `bot/handlers/ads.py`.

**DESIGN_9.6_unified_audience_wizard.md** — Purpose: **design draft** for the unified audience
engine / multi-placement / shared ad+broadcast wizard (written before code, per Hard Rule 4). ·
Read when: extending audiences, placements, or the ad/broadcast wizard. · Related:
`services/audience_service.py`, `bot/panel/wizard.py`.

**DESIGN_COOKIE_POOL.md**
- Purpose: **design draft** for the YouTube cookie pool (multi-cookie identity/health/stats,
  egress affinity, selection strategies, cooldown + auto-recovery, admin notifications, the
  in-Telegram replace flow, statistics screen). Written before code per Hard Rule 4; Owner-
  approved direction. Introduces the `EgressId` model (`warp-1`, `proxy-res-1`) that replaces
  the bare `Egress` kind for affinity and multi-instance routing.
- Read when: touching cookies, egress routing/affinity, or the cookie admin panel.
- Related: `infrastructure/downloader/routing.py`, `deploy/ytdlp-wrapper.sh`,
  `services/admin_notification_service.py`, `deploy/VPS_DEPLOYMENT_CHANGES.md`.

**I18N_IMPLEMENTATION_REVIEW.md** — Purpose: self-contained review of the i18n system. · Read
when: adding strings or changing localization. · Related: `core/i18n.py`, `core/locales/`.

**DAILY_LIMIT_VERIFICATION.md** — Purpose: manual verification of the daily-limit reset (D-012)
and referral bonus (D-066). · Read when: touching rate limits or referral bonuses. · Related:
`services/rate_limit_service.py`, `services/referral_service.py`.

**MARKDOWN_REMOVAL_GUIDE.md** — Purpose: complete reference for stripping Markdown rendering
from bot output, if ever wanted. · Read when: changing message formatting/parse mode. · Related:
`core/i18n.py`, message senders in `infrastructure/telegram/`.

### Planning (future / historical — plans, not current truth)

**VERSION_2_MASTER_PLAN.md** — Purpose: approved planning baseline for V2 (monetization). · Read
when: scoping V2 work. Note: not all V2 items exist in code yet. · Related: `MASTER_PLAN.md`.

**SPRINT_13_PLAN.md / SPRINT_13_PROMPT.md** — Purpose: Sprint 13 plan + session prompt (admin
panel enhancements, referrals, templates, health checks). · Read when: historical context on
Sprint 13 features. · Related: `PROJECT_PROGRESS.md`.

**SPRINT_14_ADMIN_V2_PLAN.md / SPRINT_14_PROMPT.md / SPRINT_14_RESULTS.md /
SPRINT_14_REVIEW_PROMPT.md** — Purpose: Sprint 14 (Admin Panel V2) plan, implementation prompt,
results log, and review prompt. · Read when: working on admin panel V2 (history/ads/broadcast/
templates) or reviewing it. · Related: `bot/handlers/admin_panel.py`, `bot/panel/`.

### Deployment & operations (`deploy/`)

**deploy/README.md** — Purpose: **Operations Runbook** (deploy, rollback, backup, DR). · Read
when: any deploy/rollback/recovery task. · Related: `deploy/RELEASE_CHECKLIST.md`,
`deploy/docker-compose.prod.yml`.

**deploy/VPS_DEPLOYMENT_CHANGES.md** — Purpose: the **live production VPS** log — every problem
hit, root cause, fix, and the Windows/paramiko deploy workflow; names the host and procedure
(no secrets). · Read when: deploying to / debugging the current VPS. · Related: `deploy/README.md`,
`deploy/docker-compose.prod.yml`, `deploy/yt-dlp.conf`.

**deploy/RAILWAY_DEPLOYMENT.md** — Purpose: how to deploy on Railway (alternative host). · Read
when: deploying to Railway. · Related: `deploy/README.md`.

**deploy/LOCAL_BOT_API.md** — Purpose: opt-in self-hosted 2 GB Telegram Bot API (raises the
50 MB upload cap). · Read when: touching upload limits / `BOT_API_BASE_URL`. · Related:
`deploy/docker-compose.prod.yml`.

**deploy/PRODUCTION_VALIDATION.md** — Purpose: post-deploy end-to-end validation checklist. ·
Read when: after any deploy, before opening to users. · Related: `deploy/SMOKE_TEST.md`.

**deploy/RELEASE_CHECKLIST.md** — Purpose: the ordered release procedure (gates → build →
migrate → deploy → verify). · Read when: cutting a release. · Related: `deploy/SMOKE_TEST.md`.

**deploy/SMOKE_TEST.md** — Purpose: quick post-deploy smoke test. · Read when: right after a
deploy or rollback. · Related: `deploy/PRODUCTION_VALIDATION.md`, `deploy/smoke-test.sh`.

**deploy/LARGE_DOWNLOAD_STRESS_TEST.md** — Purpose: plan for stress-testing large/concurrent
downloads on the real deploy. · Read when: validating download-pipeline capacity. · Related:
`PERFORMANCE_REPORT.md`.

**deploy/restore-drill-report.md** — Purpose: monthly backup/restore drill log. · Read when:
doing DR drills. · Related: `deploy/README.md`.

**migrations/planned/README.md** — Purpose: explains that files under `migrations/planned/` are
non-wired planning skeletons, not live migrations. · Read when: reviewing planned schema work. ·
Related: `migrations/`, `database_reference.md`.

**SKILL.md** — Purpose: a bundled "production-engineering-mode" skill definition (working style),
not a project-content doc. · Read when: understanding the intended engineering bar. · Related: —

> **graphify-out/** and **.pytest_cache/** are generated. Use graphify via the CLI
> (`graphify query "…"`) per `CLAUDE.md`; don't hand-edit those files.

---

## Architecture Index

*Where things live (not how they work).*

| Component | Location |
|---|---|
| **Bot process** | `bot/main.py`; handlers `bot/handlers/`, keyboards `bot/keyboards/`, callbacks `bot/callbacks/`, filters `bot/filters/`, middlewares `bot/middlewares/`. Global error backstop: `bot/handlers/errors.py` — any unhandled handler exception logs `update_handling_failed` (traceback + update context) and sends the user a localized `errors.unexpected` apology |
| **API process** | `api/main.py`, `api/app.py`, `api/readiness.py`, routes `api/routes/` |
| **Workers** | `workers/main.py`; `workers/download_worker.py`, `broadcast_worker.py`, `cleanup_worker.py` |
| **Business logic (services)** | `services/` (e.g. `download_service.py`, `job_service.py`, `queue_service.py`, `url_analyzer.py`, `notification_service.py`, `history_service.py`, `ad_service.py`, `broadcast_service.py`) |
| **Domain (pure types/protocols)** | `domain/entities/`, `domain/enums/`, `domain/protocols/`, `domain/exceptions.py`, `domain/rewards.py` |
| **Database** | `infrastructure/database/` — `engine.py`, `session.py`, `models/`, `repositories/`, `partitioning.py`, `maintenance.py`; migrations in `migrations/versions/` |
| **Redis** | `infrastructure/redis/` (queue + cache); key names in `core/redis_keys.py` |
| **Download pipeline** | Analyze: `services/url_analyzer.py` + `services/format_extraction.py`. Engine: `infrastructure/downloader/` — `registry.py` (provider selection/failover), `routing.py` (per-platform proxy/WARP/direct egress), `providers/ytdlp_provider.py`, `ffmpeg_client.py`. Orchestration: `services/download_service.py` + `workers/download_worker.py`. Config: `deploy/yt-dlp.conf`, `deploy/ytdlp-wrapper.sh` |
| **Advertisement system** | `services/ad_service.py`, `services/caption_ad_mixer.py`, `bot/handlers/ads.py`, `infrastructure/database/repositories/advertisement.py`, `infrastructure/database/ad_event_recorder.py` |
| **Broadcast system** | `services/broadcast_service.py`, `services/audience_service.py`, `workers/broadcast_worker.py`, `infrastructure/database/audience_query.py` |
| **History** | `services/history_service.py`, `bot/handlers/history.py`, `bot/keyboards/history.py` |
| **Admin Panel** | `bot/handlers/admin_panel.py`, `admin_wizard.py`, `admin.py`; shared panel UI in `bot/panel/` (`registry.py`, `states.py`, `ui.py`, `wizard.py`); HTTP admin in `api/routes/admin.py`; `services/admin_service.py`; templates `infrastructure/database/message_template_store.py` |
| **Localization (i18n)** | `core/i18n.py` + catalogs `core/locales/en.json`, `core/locales/ar.json` |
| **Configuration** | `core/config.py` (env-driven `Settings`), `core/constants.py`, `core/environment.py` |
| **Admin notifications** | `services/admin_notification_service.py` — fans out important events (new user, block/return, ban/unban, broadcast published) to the Owner + all Moderators in each recipient's locale. Hooked from `services/user_service.py` (new user, ban/unban, block/return) and `bot/handlers/membership.py` (real-time `my_chat_member` block/unblock); broadcast hook in `bot/handlers/admin_panel.py`. Recipients via `UserRepository.list_staff()`. i18n keys `adminnotify.*` in `core/locales/{en,ar}.json` |
| **Monitoring** | `api/readiness.py` (`/v1/ready`), `core/metrics.py`, `core/alerting.py` (CRITICAL→Telegram alerts + `BurstDetector` — ≥5 failed analyses in 10 min fire one `analyze_failure_burst` CRITICAL), `core/sentry.py`; uptime-kuma container in the compose stack |
| **Logging** | `core/logging.py` (structured JSON logs to stdout; correlation ids; secret scrubbing). Every meaningful event logs a consistent entry (`admin_event kind=…`, `download_requested`, `job_queued`, download/queue/worker failures, `bot/worker_starting`/`_stopped`, …). URL-analysis events (`download_requested`, `analyze_*` failures) carry `platform` + `url_host` + a short `url_hash` — never the full URL — so per-site failures are diagnosable from logs. Analysis failures are ALSO persisted to the `error_logs` table via `services/error_log_service.py` (survives log rotation; browse via `/v1/admin/errors` or SQL) Prod compose caps the json-file log (20 MB × 10). Review via `docker logs` (grep/jq-searchable) |

---

## Configuration Index

| File | Used for |
|---|---|
| `core/config.py` | The real config surface — all settings as an env-driven `Settings` (aliases like `BOT_TOKEN`, `YTDLP_PROXY`, `WORKER_COUNT`, `CACHE_METADATA_TTL`). Start here for "what can be configured". |
| `.env.example` | Template of local/dev env vars. Copy to `.env` (gitignored). |
| `.env.production.example` | Template of production env vars. Copy to `deploy/.env.production` on the server (never committed). |
| `pyproject.toml` | Project metadata, dependencies (incl. pinned `aiogram`, `yt-dlp`), and tool config (ruff, pytest). |
| `mypy.ini` | Type-checking configuration. |
| `alembic.ini` + `migrations/` | Database migrations (`migrations/env.py`, `migrations/versions/`). |
| `deploy/docker-compose.yml` | Local/dev Docker stack. |
| `deploy/docker-compose.prod.yml` | Production stack (13 services: bot/worker/api, postgres/redis/pgbouncer, bot-api, WARP pool + HAProxy LB, bgutil PO-token, uptime-kuma). Use the `bot-api` profile. |
| `deploy/Dockerfile.bot` · `Dockerfile.worker` · `Dockerfile.api` | Per-process images (worker also bakes ffmpeg + aria2 + Deno/POT). |
| `deploy/yt-dlp.conf` | yt-dlp runtime config (POT provider, EJS, retries). **Egress proxy is chosen per platform in code** (`routing.py`), not here. |
| `deploy/ytdlp-wrapper.sh` | Wraps yt-dlp to give each run a private cookie copy. |
| `deploy/haproxy-warp.cfg` | HAProxy SOCKS load-balancer for the WARP pool. |
| `deploy/migrate.sh` · `smoke-test.sh` · `monitor-resources.sh` · `capture-logs.sh` | Operational helper scripts. **Run `capture-logs.sh` first in every deploy** — it archives container logs to `/opt/telegram-bot/logs` (gzipped, 14-day retention); recreating a container destroys its logs, which has already cost one root-cause investigation. |

---

## Development Resources

*Where things are documented — no secrets here.*

- **GitHub repositories:** two remotes on the live worktree — `origin` (xAndReWxx) and
  `second` (andrewbahgat5-arch). Push to both. Crossed-account 403 is intermittent; retry.
- **Deployment (current VPS):** `deploy/VPS_DEPLOYMENT_CHANGES.md` — host, procedure, and the
  Windows/paramiko upload workflow. **Credentials are NOT in the repo** (kept in the operator's
  secure notes / `deploy/.env.production` on the server).
- **Deployment (Railway):** `deploy/RAILWAY_DEPLOYMENT.md`.
- **Operations / rollback / DR:** `deploy/README.md`.
- **Docker:** `deploy/docker-compose*.yml`, `deploy/Dockerfile.*`. Prod bring-up:
  `cd /opt/telegram-bot/deploy && docker compose --profile bot-api -f docker-compose.prod.yml up -d`.
- **Environment setup (dev):** copy `.env.example` → `.env`; `pip install -e .`; Postgres + Redis
  (compose). See `deploy/README.md`.
- **Migrations:** `alembic upgrade head` (or `deploy/migrate.sh`); create with
  `alembic revision --autogenerate -m "…"`. See `database_reference.md` + `migrations/`.
- **Testing:** `pytest tests/unit` (fast), plus `tests/integration/` and `tests/e2e/`.
  Record outcomes in `TEST_RESULTS.md`.
- **Codebase navigation:** prefer `graphify query "…"` / `graphify path` / `graphify explain`
  (see `CLAUDE.md`) over raw grep for architecture questions.

---

## Important Rules

- **MASTER_PLAN is law.** Locked decisions (`D-0xx`) must not be violated. When in doubt, read it
  and, for schema-affecting changes, design first (Hard Rule 4 — see `DESIGN_9.6_*` as the model).
- **Respect the layering.** `domain` has no I/O; `services` hold reusable business logic;
  `infrastructure` are the only I/O adapters; `bot`/`api`/`workers` are thin entry processes that
  **parse input and delegate to services**. Never import `infrastructure` directly from `bot`
  handlers — depend on `domain/protocols/` and factories wired at the composition root
  (`bot/main.py`, `workers/main.py`, `api/main.py`).
- **Don't rewrite the reusable services.** Handlers must call `services/…`, not re-implement
  logic. The download engine is provider-abstracted: services go through `DownloaderRegistry`
  and **never name a provider** (D-029).
- **i18n parity is mandatory.** Every user-facing string goes through `core/i18n` `translate(key,
  locale)`; add the key to **both** `core/locales/en.json` **and** `ar.json`.
- **Files that must change together:** `en.json` + `ar.json`; a new column + its SQLAlchemy model +
  an Alembic migration; any status change + `PROJECT_PROGRESS.md`; a feature + its doc/report
  (`TEST_RESULTS.md` / `SECURITY_REPORT.md` / `PERFORMANCE_REPORT.md`) — **and this index** if a
  doc or major component moves.
- **After code changes:** run `graphify update .` (AST-only, no API cost) to keep the graph fresh.
- **Secrets never get committed** (`.env*` is gitignored except the `*.example` files). Proxy /
  bot-token / DB creds live only in server env files.
- **Coding style:** match the surrounding code (structured logging via `core/logging`, typed,
  async throughout, tests alongside changes). Type-check with `mypy`, lint with `ruff`.

---

## Navigation Guide

If you're working on… → read this doc **and** go to this code.

| Working on… | Doc | Code |
|---|---|---|
| Overall design / a locked decision | `MASTER_PLAN.md` | — |
| Current status / what's done | `PROJECT_PROGRESS.md` | — |
| Download pipeline (analyze → download → deliver) | `PERFORMANCE_REPORT.md`, `deploy/LARGE_DOWNLOAD_STRESS_TEST.md` | `services/download_service.py`, `services/url_analyzer.py`, `infrastructure/downloader/` (`registry.py`, `routing.py`, `providers/ytdlp_provider.py`), `workers/download_worker.py` |
| Proxy / WARP / per-platform egress | `deploy/VPS_DEPLOYMENT_CHANGES.md` | `infrastructure/downloader/routing.py` — `plan_egress`: YouTube **metadata always over WARP**; **downloads split by size** (≤ `YTDLP_WARP_MAX_DOWNLOAD_MB`, default 500 → WARP; above → residential proxy), each with the other as fallback. `deploy/yt-dlp.conf` |
| YouTube cookies | `DESIGN_COOKIE_POOL.md`, `deploy/VPS_DEPLOYMENT_CHANGES.md` | **Cookie pool** (Phase 1 live 2026-07-18): `services/cookie_pool_service.py` (affinity-first LRU selection, Redis lease slots, cooldown ladder), `services/cookie_classifier.py` (**allowlist** — only auth signals may reduce health; route failures never can), `services/cookie_admin_service.py` (validate → canary → CAS replace), `infrastructure/cookies/` (versioned files + session-owning repo adapter), `bot/handlers/cookies.py` (`/cookies` panel, stats, in-Telegram replace). `deploy/ytdlp-wrapper.sh` still owns the safe file mechanics (per-run copy, flock, **merging** write-back) and now honours `$YTDLP_COOKIE_FILE`. Material lives only under `deploy/secrets/cookies.d/` on the server (git-ignored) |
| Queue / jobs | `MASTER_PLAN.md` | `services/queue_service.py`, `services/job_service.py`, `infrastructure/redis/` |
| Advertisements | `ADS_SCHEDULING.md`, `ADS_MANUAL_TEST.md` | `services/ad_service.py`, `services/caption_ad_mixer.py`, `bot/handlers/ads.py` |
| Broadcast | `SPRINT_14_ADMIN_V2_PLAN.md`, `DESIGN_9.6_unified_audience_wizard.md` | `services/broadcast_service.py`, `services/audience_service.py`, `workers/broadcast_worker.py` |
| History | `SPRINT_14_ADMIN_V2_PLAN.md` | `services/history_service.py`, `bot/handlers/history.py`, `bot/keyboards/history.py` |
| Admin Panel | `SPRINT_14_ADMIN_V2_PLAN.md`, `SPRINT_14_RESULTS.md` | `bot/handlers/admin_panel.py`, `bot/panel/`, `api/routes/admin.py` |
| Localization | `I18N_IMPLEMENTATION_REVIEW.md` | `core/i18n.py`, `core/locales/{en,ar}.json` |
| Database / migrations | `database_reference.md`, `migrations/planned/README.md` | `infrastructure/database/`, `migrations/` |
| Rate limits / referrals / rewards | `DAILY_LIMIT_VERIFICATION.md` | `services/rate_limit_service.py`, `services/referral_service.py`, `services/reward_service.py` |
| Commands / access model | `COMMANDS.md` | `bot/handlers/`, `domain/enums/user_role.py` |
| Deploy / release / rollback | `deploy/README.md`, `deploy/RELEASE_CHECKLIST.md`, `deploy/VPS_DEPLOYMENT_CHANGES.md` | `deploy/docker-compose.prod.yml`, `deploy/Dockerfile.*` |
| Security review | `SECURITY_REPORT.md` | `core/security.py`, `bot/filters/`, `api/routes/admin.py` |
| Message formatting / Markdown | `MARKDOWN_REMOVAL_GUIDE.md` | `infrastructure/telegram/`, `core/i18n.py` |
| V2 / monetization scoping | `VERSION_2_MASTER_PLAN.md` | — |
