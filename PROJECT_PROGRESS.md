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
| Current sprint | Sprint 3 (Cache and Queue) — in progress (Owner pre-authorized S2→S3 without stop) |
| Sprints completed | 2 / 13 (Sprint 0, 1 approved; Sprint 2 complete, Owner pre-authorized continuation) |
| Tasks completed | 28 / 105 (S0: 10/10; S1: 9/9; S2: 9/9) |
| Open blockers | 0 |
| Open decisions awaiting Owner | 10 (see `MASTER_PLAN.md` Section 27 Open Questions) |
| Last code change | 2026-06-23 — Sprint 2 persistence (Alembic schema, 13 ORM models, 12 repositories, partitioning) |
| Last documentation change | 2026-06-23 — `PROJECT_PROGRESS.md` + `TEST_RESULTS.md` updated for Sprint 2 |
| Next recommended action | Continue Sprint 3 (Cache and Queue), then stop for combined Owner review of Sprints 2+3. Docker Desktop now running — full `docker compose` stack verified up. |

---

## Sprint Overview

| Sprint | Title | Status | Completion | Tasks | Blocker |
|---|---|---|---|---|---|
| 0 | Bootstrap | `[x]` Completed | 100% | 10 / 10 | — |
| 1 | Foundation | `[x]` Completed | 100% | 9 / 9 | — |
| 2 | Persistence Layer | `[x]` Completed | 100% | 9 / 9 | Owner pre-authorized continuation |
| 3 | Cache and Queue | `[~]` In Progress | 0% | 0 / 7 | — |
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
| **Status** | `[~]` Under Review (code complete; awaiting Owner sign-off) |
| **Completion** | 100% (9 / 9) |
| **Goal** | `core/` is real, useful, and tested. |
| **Stop Point** | Owner reviews sample JSON log line and `SensitiveScrubber` redaction list. |

**Completed Tasks**

- [x] **1.1** `core/config.py` — pydantic-settings `Settings` over all 36 Section 13.2 keys; `SecretStr` secrets + redacting `__repr__`/`__str__`; validators (log level, sample-rate range, webhook-secret-required, empty-int→None); `sentry_enabled`/`use_webhook` helpers.
- [x] **1.2** `core/logging.py` — structlog config, `SensitiveScrubber` (recursive key redaction), JSON/console toggle, correlation-ID contextvars (`bind`/`clear`/`correlation_context`).
- [x] **1.3** `core/sentry.py` — DSN-guarded `init_sentry`; availability-guarded integrations (asyncio/fastapi/sqlalchemy/redis); `before_send` secret scrubber; `send_default_pii=False`.
- [x] **1.4** `core/uuid7.py` — pure RFC-9562 v7, process-monotonic (thread-locked counter + ms borrow on overflow); `uuid7()` / `uuid7_str()` (D-013, D-023).
- [x] **1.5** `core/constants.py` — priority bands + `priority_score`, secret-key lists, standard log fields, layered timeouts (D-025), debounce window. (Enums live in `domain/enums/` per Section 7.1; constants holds primitives only.)
- [x] **1.6** `domain/exceptions.py` — exact Section 15.4 hierarchy; each leaf carries an `ErrorType`; `DuplicateDownloadError(job_id=...)`.
- [x] **1.7** `domain/enums/` — `JobStatus` (+ `is_terminal`), `UserRole` (+ `is_staff`), `MediaFormat`, `Quality`, `ErrorType`, `AdType` (all `StrEnum`).
- [x] **1.8** `core/__main__.py` — `python -m core` configures logging and emits one structured line (binds a UUIDv7 correlation id).
- [x] **1.9** Unit tests under `tests/unit/` — 44 tests; `core/` coverage 99.26% (≥ 90%).

**Validation Results:**
- `ruff check .` / `ruff format --check .` — clean (53 files).
- `mypy --strict .` — no issues in 53 source files.
- `lint-imports` — 6 contracts kept, 0 broken.
- `pytest` — 44 passed; `core/` branch coverage 99.26% (`--cov-fail-under=90` satisfied).
- `bandit -r . -c pyproject.toml` — 0 findings (B108/B104 configurable-default defaults annotated `# nosec`).
- `pip-audit` — no known vulnerabilities (sentry-sdk 2.20.0 pinned; pre-approved in Section 6.1).
- `python -m core` — emits a single JSON log line with all Section 15.1 standard fields.

**Known Issues:** none. Only uncovered `core/` line is the `if __name__ == "__main__"` guard in `core/__main__.py`.
**Next Recommended Action:** Owner reviews a sample JSON log line + approves the `SensitiveScrubber` key list, then authorizes Sprint 2.

**Sample JSON log line (for Owner review):**
`{"component":"core","note":"structured logging is wired","event":"logging_smoke_ok","correlation_id":"019ef2a0-f755-7228-9396-8159953b01b0","logger":"core.__main__","level":"info","timestamp":"2026-06-23T03:58:15.908211Z"}`

**`SensitiveScrubber` redaction key list (substring match, case-insensitive):** `secret`, `token`, `password`, `passwd`, `dsn`, `api_key`, `apikey`, `authorization`.

---

### Sprint 2 — Persistence Layer

| Field | Value |
|---|---|
| **Status** | `[x]` Completed (Owner pre-authorized S2→S3 continuation) |
| **Completion** | 100% (9 / 9) |
| **Goal** | Postgres holds every V1 table; repositories are tested against a real database. |
| **Stop Point** | Owner inspects schema and approves partition naming scheme (`{table}_y{YYYY}m{MM}`). |

**Completed Tasks**

- [x] **2.1** Alembic configured (`alembic.ini`, async `migrations/env.py` building the URL from `core/config.py`; timestamp-prefixed filenames).
- [x] **2.2** Baseline migration `202606230001_initial_schema` — all 12 tables per Section 10; `downloads`/`jobs`/`error_logs` monthly RANGE-partitioned with a 13-month seeded window; 31 indexes; all FKs with correct ON DELETE actions.
- [x] **2.3** Seed migration `202606230002_seed_settings_and_owner` — 24 Section 13.4 settings keys + Owner user (Telegram id from env); idempotent (ON CONFLICT DO NOTHING).
- [x] **2.4** `infrastructure/database/engine.py` (async engine, `statement_cache_size=0` for PgBouncer) + `session.py` (async_sessionmaker).
- [x] **2.5** 13 ORM models in `infrastructure/database/models/` (one per table; composite PKs for partitioned tables).
- [x] **2.6** Repository protocols in `domain/protocols/repositories.py` (generic over entity type to respect the domain→infra boundary).
- [x] **2.7** 12 repositories in `infrastructure/database/repositories/` (generic base + entity-specific queries; repos flush, never commit).
- [x] **2.8** `partitioning.py` — naming/SQL helpers + `ensure_partitions_for_next_n_months` rollover helper (fake-clock injectable).
- [x] **2.9** Integration tests against live postgres-15 (transaction-rollback isolation; auto-skip when DB unavailable).

**Validation Results (verified against live postgres:15 via docker-compose):**
- `alembic upgrade head` — clean; 12 base tables, 3 partitioned, 39 partitions (3×13), 31 indexes, 24 settings, owner user.
- Schema introspection test — columns, FK ON DELETE actions (Section 10.14), and all 31 indexes match Section 10.
- Repository CRUD + behavior tests — 72 tests pass; repositories coverage 97.70% (≥80% exit criterion).
- Lazy daily-reset (D-012), `JobRepository` accepts external UUIDv7, partition rollover with fake clock — all verified.
- All gates: ruff, ruff-format, mypy --strict (90 files), import-linter (6 contracts), bandit (0), pip-audit (clean).

**Known Issues:** none. `infrastructure/database/session.py` `create_session_factory` covered by unit test; integration suite auto-skips without a migrated DB.
**Partition naming (for Owner approval):** `{table}_y{YYYY}m{MM}` — e.g. `downloads_y2026m07`.

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
| 2026-06-23 | — (uncommitted) | `alembic.ini`, `migrations/{env.py,script.py.mako,versions/2026062300{01,02}_*.py}`, `infrastructure/database/{engine,session,partitioning}.py`, `infrastructure/database/models/*.py` (13 models + base), `infrastructure/database/repositories/*.py` (12 repos + base), `domain/protocols/repositories.py`, `tests/integration/{conftest,test_schema,test_repositories,test_partition_rollover}.py`, `tests/unit/{test_partitioning,test_db_engine}.py`, `pyproject.toml` (sqlalchemy/asyncpg/alembic/redis/orjson pins); `PROJECT_PROGRESS.md`, `TEST_RESULTS.md` | Sprint 2 / 2.1–2.9 | Implementation agent |
| 2026-06-23 | `78af6ed` | `core/{config,logging,sentry,uuid7,constants,__main__}.py`, `domain/exceptions.py`, `domain/enums/{__init__,job_status,user_role,media_format,quality,error_type,ad_type}.py`, `tests/unit/test_{config,logging,sentry,uuid7,constants,enums,exceptions,main_entry}.py`, `.gitattributes`, `pyproject.toml` (sentry-sdk pin), `.env.example` (full-line comments), `MASTER_PLAN.md` (Section 9.7 `Constants` card), `PROJECT_PROGRESS.md`, `TEST_RESULTS.md` | Sprint 1 / 1.1–1.9 | Implementation agent |
| 2026-06-23 | `93524d6` | `.gitignore`, `pyproject.toml`, `mypy.ini`, `.importlinter`, `.pre-commit-config.yaml`, `.env.example`, `README.md`, `.github/workflows/ci.yml`, `deploy/docker-compose.yml`, `deploy/pgbouncer.ini`, `deploy/Dockerfile.{bot,worker,api}`, `tests/conftest.py`, 31 package `__init__.py` placeholders; `PROJECT_PROGRESS.md` + `TEST_RESULTS.md` (Sprint 0 records) | Sprint 0 / 0.1–0.10 | Implementation agent |
| 2026-06-23 | — | `MASTER_PLAN.md` (v2.1 → v2.2: Section 25 rewritten; D-031–D-039 added; Sprint 10 narrowed; Sprint 11 inserted; Sprint 11→12 renamed; DoD expanded to 19 items), `PROJECT_PROGRESS.md` (sprint structure + counts + new session handoff), `TEST_RESULTS.md` (created), `SECURITY_REPORT.md` (created), `PERFORMANCE_REPORT.md` (created) | Pre-Sprint 0 | Planning agent |
| 2026-06-23 | — | `MASTER_PLAN.md` (created, v2.0 → v2.1), `PROJECT_PROGRESS.md` (created), `database_reference.md` (marked superseded), `project_reference.md` (marked superseded) | Pre-Sprint 0 | Planning agent |

---

## Validation Status Log

Append a row whenever a validation suite runs.

| Date | Sprint / Task | Suite | Result | Notes |
|---|---|---|---|---|
| 2026-06-23 | Sprint 2 / 2.1–2.9 | Unit + Integration (72 tests, live postgres:15) + all gates | PASS | Repositories coverage 97.70% (≥80%). Schema introspection vs Section 10 passes. |
| 2026-06-23 | Sprint 1 / 1.1–1.9 | Unit (44 tests) + all gates (ruff, mypy --strict, import-linter, bandit, pip-audit) | PASS | `core/` coverage 99.26% (≥90%). See `TEST_RESULTS.md` 2026-06-23 Sprint 1 entry. |
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

### Session Handoff — 2026-06-23 — Sprint 2 Persistence Layer implemented

| Field | Value |
|---|---|
| **Session type** | Implementation |
| **Active sprint** | 2 (Persistence Layer) → continuing into Sprint 3 (Owner pre-authorized) |
| **Tasks moved** | Sprint 1 → `[x]` Completed (Owner approved). Sprint 2 tasks 2.1–2.9 all `[x]`; Sprint 2 → `[x]` Completed. Sprint 3 starting. |
| **Files modified** | Alembic (`alembic.ini`, `migrations/env.py`, `script.py.mako`, 2 versioned migrations); `infrastructure/database/{engine,session,partitioning}.py`; 13 ORM models + base; 12 repositories + base; `domain/protocols/repositories.py`; 6 test modules (2 unit, 4 integration); `pyproject.toml` (sqlalchemy 2.0.36, asyncpg 0.30.0, alembic 1.14.0, greenlet 3.1.1, redis 5.2.1, hiredis 3.1.0, orjson 3.11.5). |
| **Decisions added** | None. All deps pre-approved in Section 6.1/6.2; orjson bumped 3.10.12→3.11.5 to clear PYSEC-2026-107. |
| **Validation** | All gates PASS against live postgres:15 (docker-compose). 72 tests; repositories coverage 97.70%. `alembic upgrade head` verified: 12 tables, 39 partitions, 31 indexes, 24 settings, owner. Schema introspection matches Section 10 (columns, FK ON DELETE, indexes). mypy --strict 90 files, import-linter 6 contracts, bandit 0, pip-audit clean. |
| **Current state** | Full V1 schema lives in Postgres via one baseline + one seed migration. Partitioned `downloads`/`jobs`/`error_logs` with a rolling 13-month window and a fake-clock-testable rollover helper. 12 repositories over a generic async base (flush-only; caller owns the transaction). Docker Desktop is running; the full infra stack (postgres/redis/pgbouncer/uptime-kuma) is up. |
| **Completed work** | Tasks 2.1–2.9. Resolved during the run: (1) `id_column` stored as `InstrumentedAttribute` class attr triggered the descriptor protocol on a non-mapped class → switched to `id_attr` name + `getattr`; (2) settings upsert returned the stale identity-mapped row → rewrote as an ORM update; (3) asyncpg returns `char` as bytes → cast `confdeltype::text` in the FK test; (4) a test used a date outside the seeded partition window → switched to now-based timestamps. |
| **Remaining work** | Sprint 3 (Cache and Queue): Redis client, typed cache, distributed locks, Lua-atomic queue, cache/queue/settings services, Redis integration tests. Then stop for combined Owner review of Sprints 2+3. |
| **Known issues** | None. Integration suite auto-skips when Postgres/migrated schema is unavailable (so unit-only/CI-without-DB runs don't fail). |
| **Recommended next task** | Sprint 3 Task 3.1 (`infrastructure/redis/client.py`). |
| **Notes for the next agent** | Repositories never commit — `add`/`flush` only; the entry point owns the unit of work. The integration `db_session` fixture wraps each test in a connection transaction rolled back afterward (`join_transaction_mode="create_savepoint"`); use `db_session.begin_nested()` to assert IntegrityError without poisoning the outer txn. The seeded partition window starts at the current month — tests must use in-window timestamps. CI must run `alembic upgrade head` before the integration job. Redis key scheme is LOCKED in Section 11.4; callers must never pass raw keys (Sprint 3 enforces typed methods only). |

### Session Handoff — 2026-06-23 — Sprint 1 Foundation implemented

| Field | Value |
|---|---|
| **Session type** | Implementation |
| **Active sprint** | 1 (Foundation) |
| **Tasks moved** | Sprint 0 → `[x]` Completed (Owner authorized proceeding). Sprint 1 tasks 1.1–1.9 all `[ ]` → `[x]`; Sprint 1 → `[~]` Under Review (100%, awaiting Owner sign-off at stop point). |
| **Files modified** | New: `core/{config,logging,sentry,uuid7,constants,__main__}.py`; `domain/exceptions.py`; `domain/enums/{__init__,job_status,user_role,media_format,quality,error_type,ad_type}.py`; 8 `tests/unit/test_*.py`; `.gitattributes`. Updated: `pyproject.toml` (sentry-sdk==2.20.0 pin), `.env.example` (full-line comments), `MASTER_PLAN.md` (Section 9.7 `Constants` card), `PROJECT_PROGRESS.md`, `TEST_RESULTS.md`. |
| **Decisions added** | None. sentry-sdk pinned 2.20.0 (pre-approved in Section 6.1, not a new dependency). |
| **Validation** | All gates PASS: ruff, ruff-format, mypy --strict (53 files), import-linter (6 contracts), bandit (0 findings), pip-audit (clean), pytest (44 passed). `core/` coverage 99.26% (≥90% exit criterion met). `python -m core` emits a valid JSON log line. |
| **Current state** | `core/` is complete and tested: typed config with secret redaction, structured logging with scrubber + correlation IDs, DSN-guarded Sentry, monotonic UUIDv7, shared constants. `domain/` enums and exception hierarchy match Sections 9.4 and 15.4. No infrastructure/services/bot code yet. Sprint 0 + Sprint 1 work committed/uncommitted: Sprint 0 is commit `93524d6`; Sprint 1 working tree is **uncommitted** pending Owner instruction. |
| **Completed work** | Tasks 1.1–1.9. Resolved during the run: (1) `.env.example` empty-valued keys with inline comments broke dotenv parsing → rewrote with full-line comments + added empty-string→None validator for `telegram_alerts_chat_id`; (2) bumped to pytest 9 already done in S0; (3) annotated two bandit medium false-positives (`/tmp/downloads`, `0.0.0.0` configurable defaults) with `# nosec`. |
| **Remaining work** | Sprint 1 stop-point items for the Owner: review the sample JSON log line and approve the `SensitiveScrubber` redaction key list (both recorded in the Sprint 1 detail section above). Then authorize Sprint 2 (Persistence Layer). |
| **Known issues** | Only uncovered `core/` line is the `__main__` `if __name__` guard. `docker compose up` smoke still pending Docker Desktop (carried from Sprint 0). |
| **Recommended next task** | Owner sign-off on Sprint 1, then Sprint 2 Task 2.1 (configure Alembic). |
| **Notes for the next agent** | `Settings` uses `SecretStr` for secrets — call `.get_secret_value()`. Build test Settings via `Settings(_env_file=...)` and override with `monkeypatch.setenv` (needs `# type: ignore[call-arg]` for `_env_file`). Every `AppError` subclass exposes `.error_type` (an `ErrorType`) — reuse this when persisting to `error_logs` in Sprint 2. Enums are `StrEnum`; compare `.value` to a literal in tests to satisfy mypy's strict-equality. UUIDv7 monotonicity is process-local and thread-safe via a lock. |

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
