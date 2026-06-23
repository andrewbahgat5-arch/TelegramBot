# Project Progress Tracking

> **Document Status:** LIVE · Single Source of Truth for implementation status
> **Companion Documents:** `MASTER_PLAN.md` (architecture, sprint plan, locked decisions), `TEST_RESULTS.md`, `SECURITY_REPORT.md`, `PERFORMANCE_REPORT.md`
> **Last Updated:** 2026-06-23 (v2.2 alignment)
> **Project Phase:** Pre-Sprint 0 (planning complete; no code yet)
>
> Update this file on **every** task status change. Never let it drift from reality.

---

## How to Use This File

### For a new AI agent joining the project

1. Read `MASTER_PLAN.md` Section 1 (AI Agent Execution Rules) — non-negotiable.
2. Read this file's **Current Project State** section below.
3. Read this file's **Most Recent Session Handoff** to learn what the previous agent left.
4. Read this file's **Next Recommended Action** to know where to resume.
5. Do not start work on a task that is not the next recommended action without Owner approval.

### For an active AI agent

- Update the relevant task's status marker as soon as it changes.
- At task completion: fill the Completion Record (date, validation, tests, files, notes).
- At end of every session: append a Session Handoff entry.
- At end of every sprint: write a Sprint Closeout entry and stop for Owner approval.

### For the human Owner

- Use this file to verify reality.
- Mark `Under Review` items as `Completed` (or send them back as `Blocked` with a note).
- A task is never `Completed` without your sign-off where Human Verification is required.

---

## Status Legend (LOCKED)

| Marker | Meaning | Transition rules |
|---|---|---|
| `[ ]` | **Not Started** | → `[~]` when work begins. |
| `[~]` | **In Progress** | → `[x]` when DoD met + Owner sign-off where required. → `[!]` if a hard blocker appears. |
| `[!]` | **Blocked** | → `[~]` when blocker cleared. Always document blocker reason in the task line. |
| `[x]` | **Completed** | Terminal. Never reopened; new work goes in a follow-up task. |

A task may transition `[ ] → [~] → [!] → [~] → [x]`. The progression is monotonic toward completion; no `[x] → [~]` reversal.

---

## Current Project State

| Field | Value |
|---|---|
| Master Plan version | v2.2 |
| Current sprint | Sprint 0 (Bootstrap) — code complete, awaiting Owner sign-off at stop point |
| Sprints completed | 0 / 13 (Sprint 0 under review) |
| Tasks completed | 10 / 105 (all Sprint 0 tasks) |
| Open blockers | 0 |
| Open decisions awaiting Owner | 10 (see `MASTER_PLAN.md` Section 27 Open Questions) |
| Last code change | 2026-06-23 — Sprint 0 scaffold (layout, tooling, CI, Docker, `.env.example`) |
| Last documentation change | 2026-06-23 — `PROJECT_PROGRESS.md` + `TEST_RESULTS.md` updated for Sprint 0 completion |
| Next recommended action | **Owner reviews `pyproject.toml`, `deploy/docker-compose.yml`, `.github/workflows/ci.yml` and approves Sprint 0.** Then start Sprint 1 Task 1.1. Owner action still open: start Docker Desktop to run the `docker compose up` smoke; confirm OQ-2 (CI provider). |

---

## Sprint Overview

| Sprint | Title | Status | Completion | Tasks | Blocker |
|---|---|---|---|---|---|
| 0 | Bootstrap | `[~]` Under Review | 100% | 10 / 10 | awaiting Owner sign-off |
| 1 | Foundation | `[ ]` Not Started | 0% | 0 / 9 | depends on S0 |
| 2 | Persistence Layer | `[ ]` Not Started | 0% | 0 / 9 | depends on S1 |
| 3 | Cache and Queue | `[ ]` Not Started | 0% | 0 / 7 | depends on S2 |
| 4 | User Identity | `[ ]` Not Started | 0% | 0 / 9 | depends on S2, S3 |
| 5 | URL Analyzer + Provider Abstraction | `[ ]` Not Started | 0% | 0 / 11 | depends on S2, S3 |
| 6 | Job Pipeline (single-user) | `[ ]` Not Started | 0% | 0 / 10 | depends on S4, S5 |
| 7 | Fan-Out and Resend | `[ ]` Not Started | 0% | 0 / 4 | depends on S6 |
| 8 | Admin and Ops | `[ ]` Not Started | 0% | 0 / 3 | depends on S7 |
| 9 | Smart Advertisements | `[ ]` Not Started | 0% | 0 / 4 | depends on S7 |
| 10 | Observability and Backup | `[ ]` Not Started | 0% | 0 / 8 | depends on S9 |
| 11 | Testing Framework, Security, Load and Stress | `[ ]` Not Started | 0% | 0 / 14 | depends on S10 |
| 12 | Launch Readiness | `[ ]` Not Started | 0% | 0 / 7 | depends on S11 |
| **Total** |  |  | **0%** | **0 / 105** |  |

Sprint definitions (goal, scope, exit criteria, human verification, risks, testing) live in `MASTER_PLAN.md` Section 23. This file holds only the live tracking.

---

## Sprint Details

Each task line carries its status marker. To start a task, change `[ ]` to `[~]`. To complete, change to `[x]` and fill the Completion Record.

---

### Sprint 0 — Bootstrap

| Field | Value |
|---|---|
| **Status** | `[~]` Under Review (code complete; awaiting Owner sign-off) |
| **Completion** | 100% (10 / 10) |
| **Goal** | A repository in which every later sprint can land code with zero infrastructure friction. |
| **Stop Point** | Owner reviews `pyproject.toml`, `docker-compose.yml`, CI workflow. Approval required before Sprint 1. |

**Completed Tasks**

- [x] **0.1** Initialize git repo; `.gitignore` for Python, IDE, `.env`, temp files. → `git init` (branch `main`); `.gitignore`.
- [x] **0.2** Create `pyproject.toml` with Section 6.1/6.2 deps needed for Sprint 0. → `pyproject.toml` (exact pins: pydantic 2.11.7, pydantic-settings 2.7.1, structlog 25.4.0; dev: ruff 0.9.10, mypy 1.15.0, pytest 9.0.3, pytest-asyncio 1.4.0, pytest-cov 6.0.0, import-linter 2.3, pip-audit 2.7.3, bandit 1.8.3, pre-commit 4.1.0).
- [x] **0.3** Create directory tree per Section 7 with `__init__.py` placeholders, incl. all 7 `tests/` subdirs. → 31 packages with empty `__init__.py`; `migrations/versions`, `deploy`, `.github/workflows`.
- [x] **0.4** Add `ruff` config (in `pyproject.toml`), `mypy.ini` (strict), `.pre-commit-config.yaml`.
- [x] **0.5** Add CI workflow → `.github/workflows/ci.yml` (3 jobs: quality [ruff/format/mypy/import-linter], tests [pytest], security [pip-audit/bandit]).
- [x] **0.6** Add `import-linter` config enforcing Section 8 dependency rules; CI runs it. → `.importlinter` (6 contracts; composition-root exception per Section 8.2).
- [x] **0.7** Add `.env.example` listing every key from Section 13.2. → all 36 keys present, in section order.
- [x] **0.8** Add `deploy/docker-compose.yml` with postgres-15, redis-7, pgbouncer, uptime-kuma. → + `deploy/pgbouncer.ini`.
- [x] **0.9** Add `deploy/Dockerfile.bot`, `Dockerfile.worker`, `Dockerfile.api` skeletons. → multi-stage, slim final, non-root user; worker image installs FFmpeg.
- [x] **0.10** Add `MASTER_PLAN.md` reference and quick-start to `README.md`. → `README.md`.

**In Progress Tasks:** none.
**Blocked Tasks:** none.
**Validation Results:**
- `ruff check .` — clean.
- `ruff format --check .` — 32 files formatted.
- `mypy --strict .` — no issues in 32 source files.
- `lint-imports` — 6 contracts kept, 0 broken.
- `pytest` — 0 collected, exit 0 (empty-tree guard in `tests/conftest.py`).
- `pip-audit` — no known vulnerabilities (bumped pytest 8.3.5 → 9.0.3 to clear GHSA-6w46-j5rx-g56g).
- `bandit -r . -c pyproject.toml` — 0 findings across 23 source files.
- `docker compose config` — valid; 4 services (postgres, pgbouncer, redis, uptime-kuma).

**Known Issues:**
- `docker compose up -d` (exit-criteria item) not yet executed: Docker Desktop daemon was not running on the build host. Compose file validated via `docker compose config`. Owner action: start Docker Desktop and run the up/down cycle.
- CI green-on-`main` exit criterion is pending the first push to the remote (no remote configured yet; OQ-2 confirmation of CI provider outstanding).

**Next Recommended Action:** Owner reviews `pyproject.toml`, `deploy/docker-compose.yml`, `.github/workflows/ci.yml`, runs the `docker compose up`/`down` cycle, and approves Sprint 0. Then begin Sprint 1 Task 1.1 (`core/config.py`).

---

### Sprint 1 — Foundation

| Field | Value |
|---|---|
| **Status** | `[ ]` Not Started |
| **Completion** | 0% (0 / 9) |
| **Goal** | `core/` is real, useful, and tested. |
| **Stop Point** | Owner reviews sample JSON log line and `SensitiveScrubber` redaction list. |

**Pending Tasks**

- [ ] **1.1** Implement `core/config.py` (pydantic-settings, all env keys, secret redaction in `__repr__`).
- [ ] **1.2** Implement `core/logging.py` (structlog, `SensitiveScrubber`, JSON/console toggle, correlation context).
- [ ] **1.3** Implement `core/sentry.py` (SDK init guarded on DSN; integrations; `before_send` scrubber).
- [ ] **1.4** Implement `core/uuid7.py` (D-013, D-023).
- [ ] **1.5** Implement `core/constants.py` (priorities, role values, etc.).
- [ ] **1.6** Implement `domain/exceptions.py` matching Section 15.4 hierarchy.
- [ ] **1.7** Implement `domain/enums/` (`JobStatus`, `UserRole`, `MediaFormat`, `Quality`, `ErrorType`, `AdType`).
- [ ] **1.8** Wire `core/logging.py` into a tiny `__main__` test entry that emits one structured log line.
- [ ] **1.9** Unit tests for each `core/` module (coverage ≥ 90%).

**Validation Results:** pending.
**Known Issues:** none.
**Next Recommended Action:** wait for Sprint 0 approval.

---

### Sprint 2 — Persistence Layer

| Field | Value |
|---|---|
| **Status** | `[ ]` Not Started |
| **Completion** | 0% (0 / 9) |
| **Goal** | Postgres holds every V1 table; repositories are tested against a real database. |
| **Stop Point** | Owner inspects schema and approves partition naming scheme. |

**Pending Tasks**

- [ ] **2.1** Configure Alembic; connection from `core/config.py`.
- [ ] **2.2** Baseline migration: tables 1–12 per Section 10; monthly partitions for `downloads`/`jobs`/`error_logs`; all indexes and FKs.
- [ ] **2.3** Seed migration: settings keys (Section 13.4) + Owner user.
- [ ] **2.4** `infrastructure/database/engine.py` and `session.py` (async).
- [ ] **2.5** ORM models in `infrastructure/database/models/` (one per table).
- [ ] **2.6** Repository protocols in `domain/protocols/repositories.py`.
- [ ] **2.7** Repository implementations in `infrastructure/database/repositories/` (all 12 + `JobWaiterRepository`).
- [ ] **2.8** Partition rollover helper (`ensure_partitions_for_next_n_months`).
- [ ] **2.9** Integration tests against postgres-15 (CI service container).

**Validation Results:** pending.
**Known Issues:** none.
**Next Recommended Action:** wait for Sprint 1 approval.

---

### Sprint 3 — Cache and Queue

| Field | Value |
|---|---|
| **Status** | `[ ]` Not Started |
| **Completion** | 0% (0 / 7) |
| **Goal** | Every Redis interaction goes through the documented key scheme and is testable. |
| **Stop Point** | Owner confirms queue priorities behave correctly under mixed-batch hand test. |

**Pending Tasks**

- [ ] **3.1** `infrastructure/redis/client.py` (connection manager, separate DBs).
- [ ] **3.2** `infrastructure/redis/cache.py` (`CacheProtocol`; typed methods only — no raw keys from callers).
- [ ] **3.3** `infrastructure/redis/locks.py` (distributed lock + token foreign-release rejection).
- [ ] **3.4** `infrastructure/redis/queue.py` (`QueueProtocol`; atomic dequeue via Lua).
- [ ] **3.5** `services/cache_service.py` and `services/queue_service.py` (thin wrappers).
- [ ] **3.6** `services/settings_service.py` (read-through cache, type-cast, write-through invalidation).
- [ ] **3.7** Integration tests against real Redis.

**Validation Results:** pending.
**Known Issues:** none.

---

### Sprint 4 — User Identity

| Field | Value |
|---|---|
| **Status** | `[ ]` Not Started |
| **Completion** | 0% (0 / 9) |
| **Goal** | Every Telegram update results in a properly authenticated, throttled handler call. |
| **Stop Point** | Owner sends `/start` from owner account → confirms `owner` role. Second account → `user` role. Ban/unban test passes. |

**Pending Tasks**

- [ ] **4.1** `services/user_service.py` (upsert, role, ban/unban with audit retention, debounced `last_activity_at`, user-cache D-014).
- [ ] **4.2** `services/rate_limit_service.py` (download cooldown, lazy daily reset, message window).
- [ ] **4.3** `bot/middlewares/logging.py` (UUIDv7 correlation binding).
- [ ] **4.4** `bot/middlewares/db_session.py` (session per update; commit/rollback).
- [ ] **4.5** `bot/middlewares/auth.py` (load user; reject banned).
- [ ] **4.6** `bot/middlewares/throttle.py` (`rate_limit_messages_per_minute`).
- [ ] **4.7** `bot/filters/role_filter.py` (declarative role gating).
- [ ] **4.8** `bot/handlers/start.py` and `bot/handlers/help.py` (minimal, prove pipeline).
- [ ] **4.9** `bot/main.py` composition root.

**Validation Results:** pending.
**Known Issues:** none.

---

### Sprint 5 — URL Analyzer + Provider Abstraction

| Field | Value |
|---|---|
| **Status** | `[ ]` Not Started |
| **Completion** | 0% (0 / 11) |
| **Goal** | Given a URL, the user sees a clean format/quality keyboard. The provider abstraction is fully in place (D-026). |
| **Stop Point** | Owner hand-tests 5 URLs per platform; confirms registry behavior with a fake second provider in unit tests. |

**Pending Tasks**

- [ ] **5.1** `domain/protocols/downloader.py`: `DownloaderProtocol`, `Capability` enum, `ProviderHealth`, `ProviderUnsupported`, `ProviderRetryElsewhere`.
- [ ] **5.2** `infrastructure/downloader/registry.py` (`DownloaderRegistry`) per Section 12.6.3.
- [ ] **5.3** `infrastructure/downloader/providers/ytdlp_provider.py` (sole V1 provider; `name="ytdlp"`, `supported_platforms={"*"}`, `capabilities={VIDEO, AUDIO}`, `priority=100`).
- [ ] **5.4** Background `provider_health_check_task` in `workers/main.py`.
- [ ] **5.5** `services/url_analyzer.py` (uses `DownloaderRegistry`, COALESCE merge on `metadata_json`).
- [ ] **5.6** Format-extraction post-processing (provider-agnostic).
- [ ] **5.7** `bot/keyboards/format_select.py` and `bot/keyboards/quality_select.py`.
- [ ] **5.8** `bot/callbacks/factory.py` (signed callback data).
- [ ] **5.9** Update `bot/handlers/download.py` to show format keyboard.
- [ ] **5.10** Register `YtdlpProvider` in `bot/main.py` and `workers/main.py`.
- [ ] **5.11** `import-linter` rule: nothing under `services/`, `bot/`, `workers/`, `api/` imports `yt_dlp` or any module under `infrastructure.downloader.providers.*`.

**Validation Results:** pending.
**Known Issues:** none.
**Next Recommended Action:** wait for Sprint 4 approval.

---

### Sprint 6 — Job Pipeline (single-user)

| Field | Value |
|---|---|
| **Status** | `[ ]` Not Started |
| **Completion** | 0% (0 / 10) |
| **Goal** | End-to-end download for one user, with cache. |
| **Stop Point** | Owner sends a URL → receives file. Sends same URL → instant cached delivery. |

**Pending Tasks**

- [ ] **6.1** `domain/protocols/transcoder.py`, `domain/protocols/file_sender.py`.
- [ ] **6.2** `infrastructure/downloader/ffmpeg_client.py`.
- [ ] **6.3** `infrastructure/telegram/file_sender.py`.
- [ ] **6.4** `services/job_service.py` (cache-hit, cache-miss, lock paths from Section 16.1–16.2; fan-out deferred to Sprint 7).
- [ ] **6.5** `services/download_service.py` end-to-end happy path.
- [ ] **6.6** `workers/download_worker.py` (dequeue, run, retry via `tenacity`).
- [ ] **6.7** `workers/main.py` composition root.
- [ ] **6.8** Hook `bot/handlers/download.py` post-quality callback to `JobService.request`.
- [ ] **6.9** `services/notification_service.py` happy path.
- [ ] **6.10** `CleanupWorker` minimal sweep (temp files > 60 s).

**Validation Results:** pending.
**Known Issues:** none.

---

### Sprint 7 — Fan-Out and Resend

| Field | Value |
|---|---|
| **Status** | `[ ]` Not Started |
| **Completion** | 0% (0 / 4) |
| **Goal** | Two users requesting the same content while a download is in flight both receive the file. Resend from history works. |
| **Stop Point** | Owner: two human accounts request same URL → both receive. Resend from history works. |

**Pending Tasks**

- [ ] **7.1** Update `JobService.request` to insert `job_waiters` on duplicate path.
- [ ] **7.2** Update `DownloadService` to deliver to all waiters; per-waiter `(job_id, user_id)` idempotency.
- [ ] **7.3** `services/history_service.py` (paginated read, resend).
- [ ] **7.4** `bot/handlers/history.py` and `bot/keyboards/history.py`.

**Validation Results:** pending.
**Known Issues:** none.

---

### Sprint 8 — Admin and Ops

| Field | Value |
|---|---|
| **Status** | `[ ]` Not Started |
| **Completion** | 0% (0 / 3) |
| **Goal** | Owner and Moderator administer the bot from within Telegram. |
| **Stop Point** | Owner runs every admin command and sends a 100-user broadcast. |

**Pending Tasks**

- [ ] **8.1** `services/broadcast_service.py` + `workers/broadcast_worker.py`.
- [ ] **8.2** `bot/handlers/admin.py` (`/stats`, `/ban`, `/unban`, `/userinfo`, `/broadcast`, `/settings`, `/setting_set`).
- [ ] **8.3** `/v1/admin/*` API endpoints per Section 20.2.

**Validation Results:** pending.
**Known Issues:** none.

---

### Sprint 9 — Smart Advertisements

| Field | Value |
|---|---|
| **Status** | `[ ]` Not Started |
| **Completion** | 0% (0 / 4) |
| **Goal** | Admin manages ads; ads are delivered per the algorithm. |
| **Stop Point** | Owner creates an ad, runs downloads, sees the ad, clicks the button, confirms count rises. |

**Pending Tasks**

- [ ] **9.1** `services/ad_service.py` per Section 16.7 (post-increment modulo, D-010).
- [ ] **9.2** Admin commands: `/ad_create`, `/ad_list`, `/ad_edit`, `/ad_toggle`, `/ad_delete`, `/ad_stats`, `/ad_global`.
- [ ] **9.3** Hook `DownloadService` to call `AdService.maybe_show(user)` after delivery.
- [ ] **9.4** Click-tracking callback for ads with buttons.

**Validation Results:** pending.
**Known Issues:** none.

---

### Sprint 10 — Observability and Backup

| Field | Value |
|---|---|
| **Status** | `[ ]` Not Started |
| **Completion** | 0% (0 / 8) |
| **Goal** | Production-grade across logs, metrics, alerts, and DR. (Security validation and load testing are Sprint 11.) |
| **Stop Point** | Owner reads restore-drill report; approves runbook. |

**Pending Tasks**

- [ ] **10.1** Verify Sentry from bot, worker, api processes; tags wired.
- [ ] **10.2** Implement `/v1/metrics` with all metrics in Section 15.3.
- [ ] **10.3** Telegram alerter (throttled, deduplicated).
- [ ] **10.4** `/v1/health` and `/v1/ready` per Section 15.7.
- [ ] **10.5** `CleanupWorker` full duties (partitions, temp, stale rows, retention).
- [ ] **10.6** PgBouncer wired; connection counts verified (D-020).
- [ ] **10.7** Backup-restore drill into throwaway DB; sample download flow works.
- [ ] **10.8** Operational runbook at `deploy/README.md`.

**Validation Results:** pending.
**Known Issues:** none.

---

### Sprint 11 — Testing Framework, Security Validation, Load and Stress

| Field | Value |
|---|---|
| **Status** | `[ ]` Not Started |
| **Completion** | 0% (0 / 14) |
| **Goal** | A reusable, reproducible test framework — covering security, load, stress, and Telegram E2E — is implemented and run. Production-readiness is established by simulation, not by hope. |
| **Stop Point** | Owner reviews `TEST_RESULTS.md`, `SECURITY_REPORT.md`, `PERFORMANCE_REPORT.md`; signs off Gate G-5 (Security). |

**Pending Tasks**

- [ ] **11.1** Sandbox bot + isolated test environment (D-032); `DEPLOY_ENV=test` plumbing; production-fingerprint startup assertion.
- [ ] **11.2** `tests/e2e/harness.py` — sandbox-bot client, test-account pool, deterministic action delays.
- [ ] **11.3** E2E suites under `tests/e2e/{bot_core, download_flow, cache_flow, queue_flow, error_flow}/` covering Section 25.7.
- [ ] **11.4** Named E2E scenarios S-1 through S-5 under `tests/e2e/scenarios/` (S-3 uses mocked secondary provider).
- [ ] **11.5** Security test suite under `tests/security/` covering all five categories in Section 25.9. `pip-audit` + `bandit` wired as CI gates.
- [ ] **11.6** `tests/simulation/` framework — `SimulationRunner`, `BotClient`, `MetricsCollector`, `ReportWriter`, `UserProfile` base. Production-credential rejection in `__init__`.
- [ ] **11.7** Five V1 user profiles (`Casual`, `Active`, `Heavy`, `Abuse`; `Premium` stub for V2).
- [ ] **11.8** AI-controlled traffic generators (`RandomTraffic`, `ScheduledSpike`, `PeakHour`, `Viral`, `PlatformPattern`).
- [ ] **11.9** Stress-scenario catalog under `tests/simulation/scenarios/` (ST-1 through ST-6).
- [ ] **11.10** Run load levels L1, L2, L3, L4 end-to-end; append entries to `PERFORMANCE_REPORT.md`.
- [ ] **11.11** Run stress scenarios ST-1 through ST-6; append outcomes to `PERFORMANCE_REPORT.md`.
- [ ] **11.12** Full regression + every security category run; append to `TEST_RESULTS.md` and `SECURITY_REPORT.md`.
- [ ] **11.13** Capacity-planning report (Section 25.15.7) appended to `PERFORMANCE_REPORT.md`.
- [ ] **11.14** Manual Test Catalog entries M-17 through M-22 outcomes recorded.

**Validation Results:** pending.
**Known Issues:** none.
**Next Recommended Action:** wait for Sprint 10 approval.

---

### Sprint 12 — Launch Readiness

| Field | Value |
|---|---|
| **Status** | `[ ]` Not Started |
| **Completion** | 0% (0 / 7) |
| **Goal** | Bot ready for public traffic. |
| **Stop Point** | Owner signs off on smoke tests + E2E reruns + release entries in all three report files. V1 complete. |

**Pending Tasks**

- [ ] **12.1** Deploy bot, worker, api containers to production.
- [ ] **12.2** Configure Sentry production project + Uptime Kuma monitors.
- [ ] **12.3** Production smoke tests (`/start`, cached download, fresh download, `/stats`, ad, ban/unban).
- [ ] **12.4** Re-run E2E scenarios S-1 and S-2 against production.
- [ ] **12.5** Hand off runbook to Owner.
- [ ] **12.6** Schedule first restore drill (30 days post-launch) + first L4 production-shadow load run (90 days post-launch).
- [ ] **12.7** Mark V1 complete; append release entries to `TEST_RESULTS.md`, `SECURITY_REPORT.md`, `PERFORMANCE_REPORT.md`.

**Validation Results:** pending.
**Known Issues:** none.

---

## Files Modified Log

Append a row when a PR merges. Newest first.

| Date | PR | Files Affected | Sprint / Task | Author |
|---|---|---|---|---|
| 2026-06-23 | — (uncommitted) | `.gitignore`, `pyproject.toml`, `mypy.ini`, `.importlinter`, `.pre-commit-config.yaml`, `.env.example`, `README.md`, `.github/workflows/ci.yml`, `deploy/docker-compose.yml`, `deploy/pgbouncer.ini`, `deploy/Dockerfile.{bot,worker,api}`, `tests/conftest.py`, 31 package `__init__.py` placeholders; `PROJECT_PROGRESS.md` + `TEST_RESULTS.md` (Sprint 0 records) | Sprint 0 / 0.1–0.10 | Implementation agent |
| 2026-06-23 | — | `MASTER_PLAN.md` (v2.1 → v2.2: Section 25 rewritten; D-031–D-039 added; Sprint 10 narrowed; Sprint 11 inserted; Sprint 11→12 renamed; DoD expanded to 19 items), `PROJECT_PROGRESS.md` (sprint structure + counts + new session handoff), `TEST_RESULTS.md` (created), `SECURITY_REPORT.md` (created), `PERFORMANCE_REPORT.md` (created) | Pre-Sprint 0 | Planning agent |
| 2026-06-23 | — | `MASTER_PLAN.md` (created, v2.0 → v2.1), `PROJECT_PROGRESS.md` (created), `database_reference.md` (marked superseded), `project_reference.md` (marked superseded) | Pre-Sprint 0 | Planning agent |

---

## Validation Status Log

Append a row whenever a validation suite runs.

| Date | Sprint / Task | Suite | Result | Notes |
|---|---|---|---|---|
| 2026-06-23 | Sprint 0 / 0.1–0.10 | Tooling gates (ruff, ruff-format, mypy --strict, import-linter, pytest, pip-audit, bandit) | PASS | See `TEST_RESULTS.md` 2026-06-23 entry. `docker compose up` deferred (daemon not running). |
| — | — | — | — | No business test suites have run yet. |

---

## Known Issues / Risks / Decisions Awaiting Owner

| ID | Item | Type | Blocks | Owner Action |
|---|---|---|---|---|
| OQ-1 | Sentry: self-hosted or SaaS? Per-environment DSNs? | Open question | Sprint 10 | Decide. |
| OQ-2 | CI provider (assumed GitHub Actions). | Open question | Sprint 0 | Confirm. |
| OQ-3 | Production hosting target. | Open question | Sprint 11 | Decide. |
| OQ-4 | Admin API key auth — single key or per-admin? | Open question | Sprint 8 | Decide. |
| OQ-5 | Telegram alerts channel — dedicated chat or Owner DM? | Open question | Sprint 10 | Decide. |
| OQ-6 | Object storage for temp files at scale — V1 or V3? | Open question | Sprint 10 | Decide. |
| OQ-7 | V2 roadmap document delivery date. | Open question | Pre-V2 | Provide. |
| OQ-8 | Approved supported-platform allowlist. | Open question | Sprint 5 | Provide. |
| OQ-9 | yt-dlp update cadence — monthly cron acceptable? | Open question | Sprint 5 | Confirm. |
| OQ-10 | Approver for English V1 user-facing copy. | Open question | Sprint 4 | Identify. |

Open Questions are the canonical issue board until a real one is set up. Update both this section and `MASTER_PLAN.md` Section 27 when resolving an item.

---

## Session Handoff Log

The newest handoff is at the top. Every session ends with a new entry. Never delete old entries.

### Session Handoff — 2026-06-23 — Sprint 0 Bootstrap implemented

| Field | Value |
|---|---|
| **Session type** | Implementation |
| **Active sprint** | 0 (Bootstrap) |
| **Tasks moved** | 0.1–0.10 all `[ ]` → `[x]`. Sprint 0 → `[~]` Under Review (100%, awaiting Owner sign-off at stop point). |
| **Files modified** | Created: `.gitignore`, `pyproject.toml`, `mypy.ini`, `.importlinter`, `.pre-commit-config.yaml`, `.env.example`, `README.md`, `.github/workflows/ci.yml`, `deploy/docker-compose.yml`, `deploy/pgbouncer.ini`, `deploy/Dockerfile.{bot,worker,api}`, `tests/conftest.py`, 31 package `__init__.py` placeholders. Updated: `PROJECT_PROGRESS.md`, `TEST_RESULTS.md`. |
| **Decisions added** | None. (Exact dependency pins recorded in Sprint 0 task notes; pytest pinned to 9.0.3 to satisfy `pip-audit`. No MASTER_PLAN architecture changes.) |
| **Validation** | All Sprint 0 tooling gates PASS: ruff, ruff-format, mypy --strict, import-linter (6 contracts), pytest (0 collected/exit 0), pip-audit (clean), bandit (0 findings). `docker compose config` valid. `docker compose up` deferred — daemon not running. |
| **Current state** | Repository fully scaffolded per MASTER_PLAN Section 7. Locked layer boundaries enforced by `.importlinter`. CI workflow defined for GitHub Actions. Local infra stack defined (postgres-15, redis-7, pgbouncer, uptime-kuma). No business logic yet — all packages are empty placeholders. Working tree is **not committed** (awaiting Owner instruction to commit/push). |
| **Completed work** | All 10 Sprint 0 tasks. Resolved two validation issues during the run: (1) `tests/conftest.py` guard converts pytest exit-5 (no tests) to 0 for the empty tree; (2) bumped pytest 8.3.5 → 9.0.3 + pytest-asyncio 1.4.0 to clear `pip-audit` advisory GHSA-6w46-j5rx-g56g; added venv/cache dirs to bandit `exclude_dirs`. |
| **Remaining work** | Sprint 0 stop-point items for the Owner: review `pyproject.toml` / `docker-compose.yml` / CI workflow; start Docker Desktop and run the `docker compose up`/`down` cycle; confirm OQ-2 (CI provider) and Sentry env naming; decide whether to commit + push so CI can go green on `main`. Then authorize Sprint 1. |
| **Known issues** | `docker compose up` not yet executed (Docker daemon down on build host). CI "green on main" pending first push (no git remote yet). Both are exit-criteria items requiring the Owner's environment. |
| **Recommended next task** | Owner sign-off on Sprint 0, then Sprint 1 Task 1.1 (`core/config.py`). |
| **Notes for the next agent** | The `.venv/` on the build host already has the dev toolchain installed. Run gates with `.venv/Scripts/<tool>.exe`. Dependency pins are exact in `pyproject.toml`; any change needs a Section 6.4 row + decision-log entry. Do not add runtime deps (aiogram/fastapi/sqlalchemy/etc.) until the sprint that first uses them. The empty-tree pytest guard in `tests/conftest.py` becomes inert once the first real test exists. |

### Session Handoff — 2026-06-23 — Testing, QA, Security & Simulation Framework Integration

| Field | Value |
|---|---|
| **Session type** | Planning (no code) |
| **Active sprint** | Pre-Sprint 0 |
| **Tasks moved** | None (all tasks remain `[ ]`). Task counts updated: Sprint 10 from 10 to 8 tasks; new Sprint 11 with 14 tasks; Sprint 12 (was Sprint 11) with 7 tasks. Sprint total: 13. Total tasks: 105. |
| **Files modified** | `MASTER_PLAN.md` (v2.1 → v2.2), `PROJECT_PROGRESS.md` (sprint structure + counts). |
| **Files created** | `TEST_RESULTS.md`, `SECURITY_REPORT.md`, `PERFORMANCE_REPORT.md`. |
| **Decisions added** | D-031 through D-039 (`MASTER_PLAN.md` Section 5). |
| **Validation** | n/a — no code. Cross-document references reviewed. |
| **Current state** | Testing strategy is now exhaustive and locked. Section 25 covers test-first mindset, 6-category test directory structure, fully isolated test environment, Telegram bot E2E categories + 5 named scenarios (S-1..S-5), 5 security categories, 6 load levels (L1..L6), 6 stress scenarios (ST-1..ST-6), AI Agent Validation Workflow, 8 Human Verification Gates (G-1..G-8), three append-only report files, and the User Simulation Framework (5 user profiles + 5 traffic generators + metrics catalog + capacity report template). Definition of Done expanded from 13 to 19 items. Sprint plan restructured: Sprint 10 narrowed to observability + backup; new Sprint 11 is the full testing/security/load framework; Sprint 12 is launch readiness. |
| **Completed work** | (1) Replaced Section 25 with a 16-sub-section comprehensive testing strategy; (2) added User Simulation Framework (Section 25.15) with 10 sub-sections; (3) added D-031 through D-039 to decision log; (4) updated Section 1.8 DoD from 13 to 19 items; (5) updated Section 7 repository layout for tests/ subdirs; (6) updated Sprint 0 task 0.3 to scaffold test directories; (7) narrowed Sprint 10 to 8 tasks (observability + backup); (8) added new Sprint 11 (14 tasks — full testing + security + load); (9) renumbered Sprint 11 → Sprint 12 (7 tasks — launch readiness with E2E reruns); (10) updated Section 22.1, 22.3 master execution plan; (11) updated revision history to v2.2; (12) created `TEST_RESULTS.md`, `SECURITY_REPORT.md`, `PERFORMANCE_REPORT.md` with templates and standing entries; (13) updated `PROJECT_PROGRESS.md` to reflect 13 sprints / 105 tasks / 3 new report files. |
| **Remaining work** | All implementation. The next concrete step is still Owner authorization of Sprint 0. |
| **Known issues** | 10 Open Questions (OQ-1 through OQ-10) remain. Sprint 11 will add at least one new OQ once Sprint 10 closes: the sandbox-bot account ownership and the test-environment hosting profile. |
| **Recommended next task** | Owner answers OQ-2 (CI provider) and reviews the new Sprint 0 task 0.3 (test directory scaffolding). On approval, agent starts Task 0.1. |
| **Notes for the next agent** | The three new report files are append-only. Never edit past entries; corrections add new entries that reference the prior one. The 19-item DoD applies from Sprint 1 onward — read it before opening your first PR. The User Simulation Framework lands in Sprint 11 but its directory `tests/simulation/` is scaffolded in Sprint 0. Provider abstraction (Section 12.6) remains LOCKED — no provider names in `services/`, `bot/`, `workers/`, `api/`. |

---

### Session Handoff — 2026-06-23 — Master Plan Authoring

| Field | Value |
|---|---|
| **Session type** | Planning (no code) |
| **Active sprint** | Pre-Sprint 0 |
| **Tasks moved** | None (all tasks remain `[ ]`). |
| **Files modified** | `MASTER_PLAN.md` (created v2.0; updated to v2.1 to add provider abstraction + progress-file integration), `PROJECT_PROGRESS.md` (created), `database_reference.md` / `project_reference.md` (marked superseded). |
| **Decisions added** | D-001 through D-030 (`MASTER_PLAN.md` Section 5). |
| **Validation** | n/a — no code. Cross-document consistency reviewed. |
| **Current state** | Architecture, sprint plan, governance, provider abstraction, and progress-tracking process are fully specified. The repo still contains no application code. |
| **Completed work** | (1) Audited prior reference docs; (2) authored `MASTER_PLAN.md` v2.0 (29 sections, 12 sprints, 25 decisions resolving every flagged contradiction); (3) updated to v2.1 to elevate `DownloaderRegistry` from V6 to V1, add Hard Rules 11–12, create the progress-file pipeline, add 5 new decisions (D-026–D-030), 3 extension points (EP-16–EP-18), 6 new settings keys. |
| **Remaining work** | Everything. V1 implementation has not started. The next concrete step is Owner authorization of Sprint 0. |
| **Known issues** | 10 Open Questions (OQ-1 through OQ-10) need Owner answers. Two of them block Sprint 0 (OQ-2: CI provider) and Sprint 5 (OQ-8: platform allowlist; OQ-9: yt-dlp cadence). |
| **Recommended next task** | Owner answers OQ-2 (CI provider) and reviews Sprint 0 task list (Section 23). On approval, agent starts Task 0.1. |
| **Notes for the next agent** | Read `MASTER_PLAN.md` Section 1 (AI Agent Execution Rules) before any other action. The provider abstraction in Section 12.6 is non-negotiable; do not begin Sprint 5 without internalizing it. The Decision Log (Section 5) is the audit trail — keep it current. |

---

## Templates

Copy these when adding new entries. Do not edit the templates themselves.

### Template: Task Completion Record

When you flip a task from `[~]` to `[x]`, replace its line in the sprint detail with this block:

```
- [x] **<task_id>** <task description>
  - **Completed:** YYYY-MM-DD
  - **PR:** #<number> · <url>
  - **Validation:**
    - Unit: <pass | fail with notes>
    - Integration: <pass | n/a>
    - Manual: <pass | n/a>
  - **Files affected:**
    - `path/to/file1.py` (new | modified | deleted)
    - `path/to/file2.py` (...)
  - **Implementation notes:** <brief — non-obvious decisions, link to decision log if relevant>
```

### Template: Blocker Record

When you flip a task from `[~]` to `[!]`:

```
- [!] **<task_id>** <task description>
  - **Blocked since:** YYYY-MM-DD
  - **Blocker:** <one-paragraph description>
  - **Depends on:** <what needs to happen for unblock>
  - **Workaround attempted:** <yes/no — describe>
```

### Template: Session Handoff

Append at the **top** of the Session Handoff Log:

```
### Session Handoff — YYYY-MM-DD — <one-line session title>

| Field | Value |
|---|---|
| **Session type** | Implementation | Planning | Debug | Review |
| **Active sprint** | <number> |
| **Tasks moved** | <list of task_id status transitions> |
| **Files modified** | <list> |
| **Decisions added** | <D-NNN list, or "none"> |
| **Validation** | <ran/passed/failed suites> |
| **Current state** | <one paragraph> |
| **Completed work** | <bullet list> |
| **Remaining work** | <bullet list> |
| **Known issues** | <list of new issues or "none"> |
| **Recommended next task** | <task_id> |
| **Notes for the next agent** | <anything that isn't obvious from the diff> |
```

### Template: Sprint Closeout

When a sprint reaches Definition of Done, append to the Files Modified Log and write a closeout entry under the sprint's section:

```
**Sprint Closeout — YYYY-MM-DD**

| Field | Value |
|---|---|
| **Completion** | 100% (N / N tasks) |
| **Exit criteria** | All met (or note exceptions) |
| **Human verification** | Completed by Owner on YYYY-MM-DD |
| **Test results** | Unit: <coverage %>. Integration: <pass>. Manual: <list>. |
| **Performance against SLOs** | <if applicable — see Section 2.5 of MASTER_PLAN> |
| **Files affected (cumulative)** | <list or link to summary> |
| **Lessons learned** | <bullets, candid> |
| **Carry-over to next sprint** | <list of follow-ups, or "none"> |

→ **Sprint marked `[x] Completed` by Owner on YYYY-MM-DD.**
```

---

## AI Agent Update Procedure (LOCKED)

When you (an AI agent) work on this project:

1. **On session start:** read this file's **Current Project State**, the **Most Recent Session Handoff**, and the active sprint's section. Confirm the next recommended action matches your task.
2. **On starting a task:** change its marker from `[ ]` to `[~]`. Update the sprint's **Completion** and the **Sprint Overview** table.
3. **If you hit a blocker:** change marker to `[!]`. Add a Blocker Record. Move to the next safe task or stop and report.
4. **On finishing a task:**
   - Run all validation steps from Section 1.8 of `MASTER_PLAN.md` (19 items).
   - Run the task's specific tests (unit, integration, security, e2e, regression as applicable).
   - Update the task line using the Task Completion Record template.
   - Increment the sprint's **Completion** percentage.
   - Update the **Sprint Overview** table.
   - Update the **Files Modified Log**.
   - Update the **Validation Status Log**.
   - Append to `TEST_RESULTS.md` with the suite outcome.
   - Append to `SECURITY_REPORT.md` if the task touched security.
   - Append to `PERFORMANCE_REPORT.md` if the task touched performance.
   - If the task triggered a Human Verification Gate (Section 25.13 of `MASTER_PLAN.md`), wait for Owner sign-off (`Gate <ID> approved`) in the PR.
   - Only then move to the next task.
5. **At session end:** append a Session Handoff entry at the top of the Session Handoff Log.
6. **At sprint end:** write a Sprint Closeout entry. Do not start the next sprint. Stop and wait for Owner approval.

**Never** mark a task `[x] Completed` without satisfying Definition of Done (Section 1.8 of `MASTER_PLAN.md`). The progress file's value depends on it being trustworthy.

---

## Documentation-Driven Development Rule (restated for prominence)

> Code and documentation must never diverge. If a task is not fully implemented, validated, and tested, it must not be marked completed. If `PROJECT_PROGRESS.md`, `TEST_RESULTS.md`, `SECURITY_REPORT.md`, or `PERFORMANCE_REPORT.md` claim something that is not true, that is a documentation defect and must be corrected before any new work begins.
>
> The four files together are the project's truth. A PR that should have updated one of them and didn't is **not** done.

---

> **End of `PROJECT_PROGRESS.md`.** Companion to `MASTER_PLAN.md`. Update on every status change.
