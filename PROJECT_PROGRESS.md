# Project Progress Tracking

> **Document Status:** LIVE · Single Source of Truth for implementation status
> **Companion Documents:** `MASTER_PLAN.md` (architecture, sprint plan, locked decisions), `TEST_RESULTS.md`, `SECURITY_REPORT.md`, `PERFORMANCE_REPORT.md`
> **Last Updated:** 2026-06-24 (Sprint 6 Completed — Owner sign-off after live testing)
> **Project Phase:** Sprint 6 (Job Pipeline) **Completed** and committed. Next: Sprint 7 (Fan-Out and Resend).
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
| Master Plan version | v2.2 (+ D-040, D-041, `BOT_API_BASE_URL` env var) |
| Current sprint | Sprint 7 — **`[~]` Under Review** (code complete, all gates green; awaiting Owner human-verification at the stop point). Sprint 6 Completed (Owner sign-off 2026-06-24, `ec0ac7f`). |
| Sprints completed | 6 / 13 (S0–S6 signed off; S7 code-complete, under review) |
| Tasks completed | 69 / 105 (S0–S6 = 65; S7: 4/4 code-complete, pending Owner sign-off) |
| Open blockers | 0 |
| Open decisions awaiting Owner | 9 OQs + **2 new Sprint-7 schema deviations to ratify** (see Sprint 7 Known Issues): `downloads` has no `job_id` (idempotency moved to the Redis job context) and no `media_id` (NULL-cache resend can't reconstruct → asks user to re-send). Both forced by the locked, partitioned §10.5 schema. |
| Last code change | 2026-06-24 — Sprint 7 fan-out delivery (idempotent, per-waiter progress) + `HistoryService` + history handlers/keyboard (flow 16.3). |
| Last documentation change | 2026-06-24 — Sprint 7 closeout + session handoff (this entry); TEST_RESULTS updated. |
| Next recommended action | **Owner human-verification of Sprint 7** (two accounts request the same URL within seconds → both receive it once; resend from `/history`). Then sign off Sprint 7 and authorize Sprint 8 (Admin and Ops). |

---

## Sprint Overview

| Sprint | Title | Status | Completion | Tasks | Blocker |
|---|---|---|---|---|---|
| 0 | Bootstrap | `[x]` Completed | 100% | 10 / 10 | — |
| 1 | Foundation | `[x]` Completed | 100% | 9 / 9 | — |
| 2 | Persistence Layer | `[x]` Completed | 100% | 9 / 9 | Owner pre-authorized continuation |
| 3 | Cache and Queue | `[x]` Completed | 100% | 7 / 7 | Owner pre-authorized continuation |
| 4 | User Identity | `[x]` Completed | 100% | 9 / 9 | — |
| 5 | URL Analyzer + Provider Abstraction | `[x]` Completed | 100% | 11 / 11 | Owner sign-off 2026-06-23 (`a1f16ad`) |
| 6 | Job Pipeline (single-user) | `[x]` Completed | 100% | 10 / 10 | Owner sign-off 2026-06-24 (live-tested) |
| 7 | Fan-Out and Resend | `[~]` Under Review | 100% | 4 / 4 | code complete; awaiting Owner human-verification |
| 8 | Admin and Ops | `[ ]` Not Started | 0% | 0 / 3 | depends on S7 |
| 9 | Smart Advertisements | `[ ]` Not Started | 0% | 0 / 4 | depends on S7 |
| 10 | Observability and Backup | `[ ]` Not Started | 0% | 0 / 8 | depends on S9 |
| 11 | Testing Framework, Security, Load and Stress | `[ ]` Not Started | 0% | 0 / 14 | depends on S10 |
| 12 | Launch Readiness | `[ ]` Not Started | 0% | 0 / 7 | depends on S11 |
| **Total** |  |  | **66%** | **69 / 105** |  |

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
| **Status** | `[x]` Completed (Owner pre-authorized S3→S4 continuation) |
| **Completion** | 100% (7 / 7) |
| **Goal** | Every Redis interaction goes through the documented key scheme and is testable. |
| **Stop Point** | Owner confirms queue priorities behave correctly under mixed-batch hand test. |

**Completed Tasks**

- [x] **3.1** `infrastructure/redis/client.py` — `create_redis_clients` builds cache (DB 0) + queue (DB 1) clients (`decode_responses=True`).
- [x] **3.2** `infrastructure/redis/cache.py` — `RedisCache` implements `CacheProtocol` primitives (`get`/`set`/`delete`/`incr_with_ttl`); keys built only via `core/redis_keys.RedisKeys`.
- [x] **3.3** `infrastructure/redis/locks.py` — `RedisLock` (`SET NX EX` + token); release is a compare-and-delete Lua script (foreign-release rejection).
- [x] **3.4** `infrastructure/redis/queue.py` — `RedisQueue` implements `QueueProtocol`; Lua-atomic dequeue (ZPOPMIN + SADD active).
- [x] **3.5** `services/cache_service.py` (typed methods only — no raw keys) + `services/queue_service.py` (priority-band scoring, Section 12.2).
- [x] **3.6** `services/settings_service.py` — read-through cache, type-cast by `value_type`, write-through invalidation.
- [x] **3.7** Integration tests under `tests/integration/` (cache, locks, queue incl. 1000-job concurrent dequeue, settings service) against real Redis + Postgres.
- Plus: `core/redis_keys.py` (LOCKED Section 11.4 scheme, one helper per key); `domain/protocols/{cache,queue}.py`.

**Validation Results (verified against live redis:7 + postgres:15):**
- 92 tests pass (53 unit, 39 integration). `infrastructure/redis` coverage 100% (≥80% exit criterion); services 92–100%.
- Queue priority ordering (HIGH<NORMAL<LOW at same instant), FIFO within band, and 1000-job concurrent dequeue across 3 tasks with zero duplicates — all verified.
- Lock acquire blocks a second acquire; correct-token release frees it; foreign-token release rejected.
- `SettingsService.get("free_daily_limit")` returns int 10 (cast from text); read-through cache serves until `set` invalidates it.
- All gates: ruff, ruff-format, mypy --strict (105 files), import-linter (6 contracts), bandit (0), pip-audit (clean).

**Known Issues:** none. (Docker Desktop daemon on the build host was flaky mid-session — stopped twice — but the full stack is up and all integration tests executed green.)

---

### Sprint 4 — User Identity

| Field | Value |
|---|---|
| **Status** | `[x]` Completed (Owner sign-off 2026-06-23) |
| **Completion** | 100% (9 / 9) |
| **Goal** | Every Telegram update results in a properly authenticated, throttled handler call. |
| **Stop Point** | Owner sends `/start` from owner account → confirms `owner` role. Second account → `user` role. Ban/unban test passes. |

**Completed Tasks**

- [x] **4.1** `services/user_service.py` — cache-first `get_or_create_user` (D-014), owner-role assignment from config, debounced `record_activity`, `set_role`/`ban`/`unban` with audit-field retention and cache invalidation (Section 11.3). Added `UserSnapshot` entity (`domain/entities/user.py`) + repo `create_user`/`touch_last_activity` (+ protocol).
- [x] **4.2** `services/rate_limit_service.py` — `check_message_rate` (Redis 60 s window) and `check_download` (maintenance gate, effective-plan resolution, lazy daily reset D-012, daily-limit + cooldown per Section 16.5).
- [x] **4.3** `bot/middlewares/logging.py` — binds a fresh UUIDv7 correlation id per update via `core.logging.correlation_context`.
- [x] **4.4** `bot/middlewares/db_session.py` — session per update; commit on success, rollback on exception (unit-of-work boundary).
- [x] **4.5** `bot/middlewares/auth.py` — cache-first user resolution, activity record, banned-user rejection (Message + CallbackQuery), attaches `UserSnapshot` as `data["user"]`.
- [x] **4.6** `bot/middlewares/throttle.py` — enforces `rate_limit_messages_per_minute`; friendly reply on exceed.
- [x] **4.7** `bot/filters/role_filter.py` — declarative `RoleFilter(*roles)` + `StaffFilter` convenience.
- [x] **4.8** `bot/handlers/start.py` + `bot/handlers/help.py` — minimal pipeline-proving handlers (no business logic).
- [x] **4.9** `bot/main.py` — composition root: wires concretes→protocols, builds the dispatcher with the Section 9.1 middleware stack (`build_dispatcher`), long-polling default + optional webhook.

**Validation Results (unit + all gates; integration suite green where infra present):**
- 101 unit tests pass (48 new for Sprint 4); full suite 140 pass (101 unit + 39 integration). Sprint-4 module coverage: services + `UserSnapshot` 100%; middlewares/handlers/filter 97–100%; `bot/main.py` 52% (only the network-bound `main()`/`_run_webhook` entry uncovered — exercised via the human-verification bot run; `build_dispatcher` wiring is covered).
- All gates: ruff, ruff-format (124 files), mypy --strict (124 files), import-linter (6 contracts; `bot.main → infrastructure.**` composition-root exception holds), bandit (0), pip-audit (clean).

**Known Issues:**
- `bot/main.py` `main()`/`_run_webhook` are not unit-tested (require a live Telegram token + backing infra). Covered by the Owner sandbox-bot run (exit criterion 2).

**Resolved during review:** `LAST_ACTIVITY_DEBOUNCE_SECONDS` tightened 60 s → **5 s** per Owner direction, matching the Sprint 4 checklist ("write at most every 5 s per user").

**Sprint Closeout — 2026-06-23**

| Field | Value |
|---|---|
| **Completion** | 100% (9 / 9 tasks) |
| **Exit criteria** | All met. Validation suite green; bot ran against a live sandbox bot and responded to `/start` + `/help`; `import-linter` green (no service→infrastructure import). |
| **Human verification** | Completed by Owner on 2026-06-23 — `/start` from owner account → `owner` role; second account → `user` role; ban via SQL blocked the user (ban message only); unban restored access. |
| **Test results** | Unit 101 (Sprint-4 services + entity 100%; middlewares/handlers/filter 97–100%). Full suite 140 (incl. 39 integration). All gates green. |
| **Files affected (cumulative)** | See Files Modified Log (Sprint 4 / 4.1–4.9 row). |
| **Lessons learned** | Services stay framework-agnostic by building `UserSnapshot` from repo rows (attribute access) — the ORM-construction stays in the repo (`create_user`). The bot must run from the worktree (its CWD wins on `sys.path`); the main checkout lacks Sprint 4 code. aiogram `AsyncMock(spec=Message)` doesn't auto-async `answer`. |
| **Carry-over to next sprint** | None. |

→ **Sprint marked `[x] Completed` by Owner on 2026-06-23.**

---

### Sprint 5 — URL Analyzer + Provider Abstraction

| Field | Value |
|---|---|
| **Status** | `[x]` Completed (Owner sign-off 2026-06-23) |
| **Completion** | 100% (11 / 11) |
| **Goal** | Given a URL, the user sees a clean format/quality keyboard. The provider abstraction is fully in place (D-026). |
| **Stop Point** | Owner hand-tests 5 URLs per platform; confirms registry behavior with a fake second provider in unit tests. |

**Completed Tasks**

- [x] **5.1** `domain/protocols/downloader.py` — `DownloaderProtocol`, `ProviderSettingsProtocol`, `Capability`/`ProviderHealth` enums, `ProviderUnsupported`/`ProviderRetryElsewhere`. Plus `domain/entities/media.py` (`MediaInfo`, `MediaFormatOption`, `DownloadedFile`) and `core/urls.py` (validate/normalize/detect-platform/extract-id).
- [x] **5.2** `infrastructure/downloader/registry.py` — candidate selection (enabled + platform + healthy, sorted `priority DESC, name ASC`), failover, retryable→DEGRADED-on-threshold with cooldown skip, in-memory health mirror + Redis persistence (`provider:health:{name}`), `refresh_health`. Implements `DownloaderProtocol` as the service-facing facade.
- [x] **5.3** `infrastructure/downloader/providers/ytdlp_provider.py` — async subprocess wrap of the `yt-dlp` binary (no `import yt_dlp`), `-J` JSON → `MediaInfo`, raw format parsing, vendor-error mapping (Section 12.6.8), `download`, `health_check`.
- [x] **5.4** `workers/main.py` — worker composition root running `provider_health_check_task` every `provider_health_check_interval_seconds`.
- [x] **5.5** `services/url_analyzer.py` — validate/normalize, `(platform, video_id)`, metadata-cache read-through, `DownloaderRegistry.extract_info` on miss, COALESCE upsert (D-011), cache write; returns `AnalyzedMedia(media_id, info)`; `analyze_by_media_id` for the callback step.
- [x] **5.6** `services/format_extraction.py` — provider-agnostic dedup (one per `(format, quality)`) + sort (video best-first, then audio).
- [x] **5.7** `bot/keyboards/format_select.py` + `quality_select.py`.
- [x] **5.8** `bot/callbacks/factory.py` — HMAC-signed `(media_id, format[, quality])` callbacks; forged/garbled data rejected (Section 14.2); within Telegram's 64-byte limit.
- [x] **5.9** `bot/handlers/download.py` — URL → format keyboard → quality keyboard; final quality pick acknowledged (Sprint 6 hooks `JobService`).
- [x] **5.10** `YtdlpProvider` registered in `bot/main.py` and `workers/main.py`; analyzer factory + signer injected as dispatcher workflow data; `download` router included.
- [x] **5.11** `import-linter` contract `providers-only-via-registry` (forbids `services/bot/workers/api` importing `infrastructure.downloader.providers`, composition-root exceptions only). yt-dlp is a subprocess, so there is no `import yt_dlp` to guard.

**Validation Results (unit + all gates; integration verified against live postgres:15 + redis:7):**
- 214 tests pass (incl. owner hand-test of real YouTube/TikTok/etc. links). Sprint-5 coverage: `core.urls` 95%, services 100%, registry 91%, `ytdlp_provider` ~90%, keyboards/handlers/callbacks 92–100%; `provider_settings` covered by integration.
- All gates: ruff, ruff-format, mypy --strict (146 files), import-linter (7 contracts — new `providers-only-via-registry` kept), bandit (0 findings), pip-audit (no new runtime dependencies; yt-dlp is a subprocessed system tool, not a Python dep).

**Bug fixed during owner validation (2026-06-23):** quality detection mislabeled non-16:9 videos. yt-dlp reports true tiers in `format_note` but real pixel heights are non-standard (4K wide = 3840×2026), so the old `height >= threshold` floor shifted every tier down one (4K shown as 1440p, real 4K dropped). Fixed `_quality_for_format` to prefer yt-dlp's `format_note` label and otherwise snap the *longer* edge to the nearest standard tier; added a parametrized regression test (`test_quality_for_format_handles_non_16x9`). Verified against the reported video: now offers 2160p…144p.

**Known Issues:**
- `bot/main.py` `main()`/`_run_webhook` and `workers/main.py` `main()` are not unit-tested (need a live token + infra); covered by the Owner sandbox run. `build_registry`/`build_dispatcher` wiring is unit-covered.
- OQ-8 (platform allowlist) and OQ-9 (yt-dlp update cadence) remain open. V1 detects platform best-effort and lets yt-dlp (`supported_platforms={"*"}`) decide; no hard allowlist gate.
- **Approx file-size labels are rough and not strictly monotonic** (owner-observed). Each tier has avc1/vp9/av01 variants of very different sizes; dedup keeps the largest, and the kept codec varies by tier (e.g. legacy muxed `18` for 360p). The numbers are also video-only (audio added at download). Cosmetic, out of Sprint 5 scope; deferred to Sprint 6 where the download/transcode path can produce consistent estimates (prefer one codec per tier + include audio).
- Audio is exposed as a single generic "Audio" option in V1. Explicit per-codec audio formats (MP3/M4A/AAC/OGG/Opus/WAV/FLAC) require FFmpeg transcoding + a domain-model change → deferred to Sprint 6.

**Sprint Closeout — 2026-06-23**

| Field | Value |
|---|---|
| **Completion** | 100% (11 / 11 tasks) |
| **Exit criteria** | Met. Owner hand-tested live URLs across platforms (analysis + format→quality keyboards + metadata-cache speed-up + bad/non-URL rejection). Registry failover/health verified with fake-second-provider unit tests. yt-dlp invocation timed/logged. `import-linter` green (providers reachable only via the registry). |
| **Human verification** | Completed by Owner on 2026-06-23 (live Telegram sandbox bot). |
| **Test results** | 214 tests pass; all gates green (ruff, mypy --strict 146 files, import-linter 7 contracts, bandit 0, pip-audit). |
| **Commits** | `a1f16ad` (Sprint 5), `99c2e9c` (handoff doc). |
| **Lessons learned** | Quality tiers must come from yt-dlp's `format_note` / nearest longer-edge, not a raw-height floor (non-16:9 4K = 3840×2026). `ClassVar` protocol members block per-instance test fakes — provider identity attrs are plain instance attributes. yt-dlp is a subprocessed system tool, not a Python dependency. |
| **Carry-over to Sprint 6** | Real download/transcode/upload + delivery; progress feedback; thumbnail preview; accurate file-size estimates; explicit per-codec audio formats. OQ-11 (50 MB bot limit vs self-hosted Bot API) to be decided first. See "Owner-requested carry-ins for Sprint 6". |

→ **Sprint marked `[x] Completed` by Owner on 2026-06-23.**

---

### Sprint 6 — Job Pipeline (single-user)

| Field | Value |
|---|---|
| **Status** | `[x]` Completed (Owner sign-off 2026-06-24 after live testing across YouTube/TikTok/Instagram) |
| **Completion** | 100% (10 / 10 + 4 Owner carry-ins + post-verification fixes) |
| **Goal** | End-to-end download for one user, with cache. |
| **Stop Point** | Owner sends a URL → receives file. Sends same URL → instant cached delivery. |

**Owner decisions taken at sprint start (2026-06-24):** self-hosted Telegram Bot API server, 2 GB cap (D-040, resolves OQ-11); all four carry-ins folded in.

**Completed Tasks**

- [x] **6.1** `domain/protocols/transcoder.py` (`TranscoderProtocol`) + `domain/protocols/file_sender.py` (`FileSenderProtocol`, `MessageSenderProtocol`, `UploadedFile`). Domain-model change (D-041): `Quality` gains audio-codec members (`mp3/m4a/aac/ogg/opus/wav/flac`); `MediaFormatOption.codec`; `AudioTarget` + `AUDIO_TARGETS` catalog in `domain/entities/media.py`.
- [x] **6.2** `infrastructure/downloader/ffmpeg_client.py` — async FFmpeg subprocess; remux (`-c:a copy`) when source matches the container, else re-encode to the target codec.
- [x] **6.3** `infrastructure/telegram/file_sender.py` — `TelegramFileSender` (upload-once → reusable `file_id`; deliver by `file_id`) + `TelegramMessageSender` (progress edits). `infrastructure/telegram/client.py` `build_bot` selects the self-hosted Bot API server when `BOT_API_BASE_URL` is set (D-040).
- [x] **6.4** `services/job_service.py` — lock → cache-hit (instant delivery + counters, 16.2) / cache-miss (claim `active_downloads`, create job + waiter, stash worker context, enqueue, 16.1) / duplicate (attach waiter; full fan-out is Sprint 7).
- [x] **6.5** `services/download_service.py` — resolve media → download (via registry) → transcode audio target → upload → `cached_files` UPSERT → per-waiter `downloads` + counters + delivery → mark complete → release lock → wipe temp. Emits `download_seconds`/`upload_seconds`/`job_processing_seconds`. `handle_failure`/`mark_retry`/`mark_permanent_failure` own the state machine.
- [x] **6.6** `workers/download_worker.py` — dequeue, one-transaction-per-job unit of work, job-level retry (`retry_queued` → up to `max_retries` → `permanently_failed`, re-enqueue at LOW).
- [x] **6.7** `workers/main.py` — composition root: shared registry/bot/file_sender/notifier/FFmpeg + per-job `DownloadService` factory; runs health-check + N download workers + cleanup worker concurrently.
- [x] **6.8** `bot/handlers/download.py` — post-quality pick sends a progress message and calls `JobService.request`; **thumbnail preview** on the format message (photo + caption, caption-aware edits); per-codec audio buttons.
- [x] **6.9** `services/notification_service.py` — **progress feedback**: edits one message through `queued → downloading → processing → uploading → ✅/❌` (state only, no percent).
- [x] **6.10** `workers/cleanup_worker.py` — minimal sweep of temp entries older than 60 s.

**Owner carry-ins — delivered:**
- **Progress feedback** — `NotificationService` (6.9) + worker stage edits.
- **Thumbnail preview** — `handle_url` sends the thumbnail with the format keyboard.
- **Accurate file-size estimates** — `services/format_extraction.py` picks one consistent video codec per tier (avc1 → vp9 → av01) and adds the best audio stream's size; sizes are now sensible/monotonic.
- **Explicit per-codec audio** (D-041) — `MediaFormatOption.codec` + `Quality` audio members + `AUDIO_TARGETS`; the codec is the persisted `quality` value, so the LOCKED `(media_id, format, quality)` cache key distinguishes codecs with no schema change.

**Validation Results (all gates green; verified against live postgres:15 + redis:7):**
- `ruff check .` / `ruff format --check .` — clean.
- `mypy --strict .` — no issues in 163 source files.
- `lint-imports` — 7 contracts kept, 0 broken (workers/bot reach infra only via their composition roots; providers only via the registry).
- `pytest` — **252 passed** (206 unit + 46 integration; +`test_file_sender` and provider/notification regressions from the post-verification round). New unit suites: `test_job_service`, `test_download_service`, `test_notification_service`, `test_cleanup_worker`, `test_download_worker`, `test_format_sizes`, `test_file_sender`; updated `test_download_handler`, `test_format_extraction`, `test_url_analyzer`, `test_ytdlp_provider`, `test_bot_composition`. New integration suite `test_pipeline_repositories` exercises the PG `ON CONFLICT…RETURNING` + lazy-`CASE` SQL.
- `bandit -r . -c pyproject.toml` — 0 findings.
- `pip-audit` — no known vulnerabilities; **no new dependencies** (FFmpeg/yt-dlp are subprocessed system tools).

**Bug found + fixed during validation (2026-06-24):** the live-DB `test_pipeline_repositories` caught `CachedFileRepository.upsert` returning a stale identity-map instance on conflict (old `file_id`/`usage_count`). Fixed with `.execution_options(populate_existing=True)` so the RETURNING values refresh the ORM object.

**Post-verification fixes (2026-06-24, Owner live-test round) — all green (252 tests):**
- **Duplicate delivery (every fresh download sent twice).** Root cause: the worker uploaded to a *storage chat = owner id*, then `send_cached` re-sent to the user; with the owner as tester that delivered the file twice (the cache-hit path used a single `send_cached`, which is why only fresh downloads doubled). Fix: the worker now **uploads directly to the first waiter** (that upload *is* their delivery) and reuses the resulting `file_id` for any additional waiters — exactly one file per user. `TelegramFileSender` no longer takes a storage chat.
- **OGG/OPUS failed + retry-looped → "download failed".** Telegram converts `.ogg`/`.opus` sent via `send_audio` into voice notes, so `message.audio` was `None` → "Telegram returned no file reference" → retryable loop ×3 → permanent fail. Fix: ogg/opus/flac are sent as **documents**; `_extract_upload` also reads `message.voice`. AAC/M4A/MP3/WAV unchanged (and no longer double-delivered).
- **TikTok (and other muxed-only sources) offered no audio.** They expose no audio-only stream, so the per-codec catalog never expanded. Fix: the provider emits a generic audio source whenever *any* stream has audio; the download uses `bestaudio/best` (extracts audio from the best muxed stream).
- **Silent high-res video (latent) + non-monotonic sizes (#7).** Video now downloads via `bestvideo[height<=H]+bestaudio` (always merges audio, never a silent single-stream). Size estimates moved into the provider: video-only += best-audio size, **muxed counted once** (the 360p>1080p double-count is gone), with a `tbr×duration` fallback when `filesize` is missing.
- **UX #9 / #8.** The bot now replies `🔍 Analyzing link…` instantly and then shows the thumbnail + title + duration + source. Progress is a **single in-place message with one percentage bar** (internal download/transcode/upload stages are no longer surfaced).
- **Videos sent as documents, not playable (round 2).** A merged `.webm` (VP9/Opus) shows as a document even via `sendVideo`. Fix: the yt-dlp selector prefers `vcodec^=avc1 + acodec^=mp4a` and the download adds `--merge-output-format mp4`, so output is a playable mp4 (H.264/AAC) inline video whenever the source offers those codecs; VP9/AV1-only tiers fall back gracefully.
- **Back button (#10).** The quality / audio-codec screen has a `⬅️ Back` row that returns to the Video/Audio choice without resending the link (new signed callback action `b`; `handle_back` rebuilds the format keyboard).
- **Title-based filenames (#11).** Delivered files are named after the sanitized media title with the correct extension (`Song Title.mp3`, `Video Title.mp4`), across all audio/video formats (`_safe_filename` in `DownloadService`).
- **Local Bot API (#12).** Code path unit-verified (`build_bot` targets the local endpoint when `BOT_API_BASE_URL` is set; public API otherwise). Config, the cloud-`logOut` token gotcha, large-file behavior, and risks (esp. **`file_id`s are server-scoped → switching endpoints invalidates the existing `cached_files`**) documented in `deploy/LOCAL_BOT_API.md`. Public API stays the default.
- **MP3 "not delivered" → self-healing cache (#13).** Root cause was **not** MP3 conversion (which works): the test session **switched bot tokens**, and Telegram `file_id`s are **bot-scoped**, so every cached MP3/M4A resend failed with `Bad Request: wrong file identifier` in the cache-hit path. Fix: `send_cached` now raises `CachedFileExpiredError` (new, `ErrorType.CACHED_FILE_EXPIRED`) when Telegram rejects a `file_id`; `JobService` delivers from cache **first**, and on that signal **evicts** the stale `cached_files` row + Redis key and **falls back to a fresh download** — self-healing across bot-token rotation, Bot-API endpoint switches, and Telegram-side expiry. DB writes/✅ now happen only after the file actually reaches the user. (Total tests now **268**: 222 unit + 46 integration.)

**Known Issues / deviations (documented):**
- **`tenacity` deferred.** Section 6.2 pre-approves `tenacity`, but it is not yet vendored in this environment; adding+importing it would break the gates. Sprint 6 implements the *validated* retry behavior (job-level `retry_queued` → up to 3 → `permanently_failed`) in the worker without it. In-process tenacity backoff can be layered later.
- **Fan-out is single-user only.** `JobService` duplicate path attaches a waiter and the `DownloadService` waiter loop already iterates all waiters, but multi-recipient delivery + per-waiter progress is Sprint 7 (Tasks 7.1/7.2).
- **`bot/main.py`/`workers/main.py` `main()` entry points** remain network-bound and unit-uncovered (covered by the Owner sandbox run). `build_dispatcher`/`make_download_service_factory` wiring is unit-covered.
- **Per-codec audio size estimates are approximate** (lossless scaled from the best lossy source; the real size is known after FFmpeg runs). Labels are prefixed `~`.

---

### Sprint 7 — Fan-Out and Resend

| Field | Value |
|---|---|
| **Status** | `[~]` Under Review (code complete, all gates green; awaiting Owner human-verification at the stop point) |
| **Completion** | 100% (4 / 4) |
| **Goal** | Two users requesting the same content while a download is in flight both receive the file. Resend from history works. |
| **Stop Point** | Owner: two human accounts request same URL → both receive. Resend from history works. |

**Completed Tasks**

- [x] **7.1** `JobService.request` duplicate path attaches the user as a `job_waiters` row (16.4) **and** registers their progress message in the Redis job context (`progress` map) so the worker edits *their* message to ✅/❌, not only the originator's. The originator is seeded into the same map at job creation.
- [x] **7.2** `DownloadService._deliver` reads every waiter and delivers once to each — the first not-yet-delivered waiter's upload is their delivery (mints the `file_id`), every other waiter gets that `file_id` via `send_cached`. **Idempotent across retries:** the minted `file_id` and the set of already-delivered `user_id`s are persisted in the Redis job context (outside the per-job DB transaction), so a retry after a partial delivery reuses the `file_id` (no re-upload → the first waiter is never re-delivered) and skips `send_cached` for anyone already delivered. `downloads` rows + counters are re-created for every waiter (they rolled back). One waiter's delivery failure is logged and skipped (risk-table mitigation), never blocking the rest. On completion/failure **all** waiters' progress messages are edited.
- [x] **7.3** `services/history_service.py` — paginated newest-first read (`HISTORY_PAGE_SIZE=5`, over-reads by one to detect the next page) and `resend`: deliver instantly from cache (bump `usage_count`, **no** new `downloads` row, 16.3 step 5); on a Telegram-rejected `file_id` evict the stale cache and fall back to a fresh `JobService.request` (16.3 step 4); on an unreconstructable row return `NEEDS_RELINK`.
- [x] **7.4** `bot/handlers/history.py` (`/history`, page nav, resend) + `bot/keyboards/history.py` (resend button per row + prev/next), wired via a new `history_service_factory` in `bot/main.py`. New signed callback actions `r` (resend `download_id`) and `h` (history page). `/history` added to `/help`.

**Owner-requested History UX (future enhancement — 2026-06-24, do NOT implement before its sprint):** a History section where the user browses previously downloaded media with **title, thumbnail, platform, and date**; tapping an entry **instantly re-sends** it. Sprint 7's 7.3/7.4 deliver the **resend mechanics + a basic list** (platform/quality/format/date, newest first); the richer browsable UI (thumbnails + titles) is the Owner's desired surface and may warrant its own dedicated sprint. NOTE: `downloads` (§10.5) carries no `title`/`thumbnail`/`media_id` columns — a thumbnail/title grid would read those from `media_metadata`, which needs a join key (`media_id`) the history row does not store. Flag for the dedicated History-UI sprint.

**Validation Results (all gates green; verified against live postgres:15 + redis:7):**
- `ruff check .` / `ruff format --check .` — clean.
- `mypy --strict .` — no issues in **170** source files.
- `lint-imports` — **7 contracts kept, 0 broken** (HistoryService depends only on services/domain; the history handler reaches infrastructure only via `bot/main.py`).
- `pytest` — **290 passed** (242 unit + 48 integration). New unit suites: `test_history_service`, `test_history_handler`; extended `test_job_service` (per-waiter progress context), `test_download_service` (fan-out to all waiters, retry-after-partial idempotency, per-waiter-failure isolation), `test_callback_factory` (resend/history actions), `test_keyboards` (history keyboard), `test_bot_composition` (4 routers). New integration tests: `DownloadRepository.get_for_user` owner-scoping + `list_for_user` newest-first pagination (live DB).
- `bandit -r . -c pyproject.toml` — 0 findings.
- `pip-audit` — no new dependencies (no `pyproject.toml` change).

**Known Issues / deviations (REQUIRE OWNER RATIFICATION — surfaced at the stop point per §1.11):**
- **Deviation A — `downloads` has no `job_id`; idempotency moved to the Redis job context.** Task 7.2 / flow 16.1 W7 specify per-waiter idempotency via `(job_id, user_id)` uniqueness in the `downloads` insert. That is **physically impossible** against §10.5 as locked: `downloads` has no `job_id` column, and it is RANGE-partitioned by `created_at`, so a Postgres unique constraint *must* include the partition key — `(job_id, user_id)` alone cannot exist. Also, a DB unique constraint would roll back with the per-job transaction, so it would not actually stop the *re-delivery* (the non-transactional Telegram send) on a retry anyway. **Resolution implemented:** idempotency lives where it can survive the rollback — the Redis job context records the minted `file_id` and the delivered `user_id`s; a retry skips re-upload and re-send. (This matches the prior session's handoff guidance to "extend the Redis job context.") No schema change. **Owner decision needed:** ratify this, or approve a future migration adding `downloads.job_id` + a partition-compatible unique index `(job_id, user_id, created_at)` (a §10/§19/§5 change).
- **Deviation B — `downloads` has no `media_id`; a truly NULL-cache resend cannot be reconstructed.** The checklist item "resend when `cached_file_id` is NULL falls back to a new download" is only partly feasible. When the `cached_files` row still exists but Telegram rejects the `file_id`, we reuse `cached_files.media_id` to queue a fresh download (this path **is** implemented and tested → `REQUEUED`). When `cached_file_id` is genuinely NULL (its parent `cached_files` row was deleted, FK `ON DELETE SET NULL`), there is **no `media_id`** anywhere on the row to reconstruct the source, so resend returns `NEEDS_RELINK` (asks the user to send the link again). **Owner decision needed:** accept the relink fallback, or approve a future migration adding `downloads.media_id` so any history row can be re-downloaded.
- **Per-stage progress for fan-out duplicates is originator-only (cosmetic).** During processing, only the originator's message shows the moving bar; **completion/failure** (✅/❌) is edited on **every** waiter's message. Surfacing live per-stage bars to every waiter would multiply Telegram edit calls; flow 16.1 only mandates `notify_completed` per waiter, which is implemented.
- **Concurrency/idempotency proven at the unit level (with fakes).** The 10-simultaneous-waiter stress and "retry after partial delivery" scenarios are covered by `test_download_service` (fan-out + idempotency) and `test_pipeline_repositories` (live SQL). The Owner human-verification step (two real accounts) remains the acceptance gate.

**Sprint Closeout — 2026-06-24**

Sprint 7 (Fan-Out and Resend) is code-complete and `[~]` Under Review. Multi-recipient fan-out now delivers a single file to every waiter on one in-flight job, idempotently across worker retries, with per-waiter completion/failure notifications. `/history` lists past downloads newest-first and resends any of them — instantly from cache (no duplicate history row) or via a fresh download when the cache is unusable. All automated gates pass (290 tests; ruff, mypy --strict 170 files, import-linter 7 contracts, bandit 0). No schema, config-key, dependency, or migration changes. Two schema deviations (no `job_id`/`media_id` on `downloads`) are documented above for Owner ratification. Stops here for Owner human-verification before Sprint 8.

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
| 2026-06-24 | — (uncommitted) | New: `services/history_service.py`; `bot/handlers/history.py`; `bot/keyboards/history.py`; `tests/unit/{test_history_service,test_history_handler}.py`. Updated: `services/{job_service,download_service,cache_service}.py` (per-waiter progress map; idempotent fan-out delivery; `add_waiter_progress`/`record_uploaded_file`/`record_delivered`); `bot/callbacks/factory.py` (`r`/`h` actions, `arg` field); `bot/main.py` (`history_service_factory` + router); `bot/handlers/help.py` (`/history`); `domain/protocols/repositories.py` (`DownloadRepositoryProtocol.get_for_user`); `infrastructure/database/repositories/download.py` (`get_for_user`, deterministic `created_at DESC, id DESC` order); `tests/unit/{_fakes,test_job_service,test_download_service,test_callback_factory,test_keyboards,test_bot_composition}.py`; `tests/integration/test_pipeline_repositories.py`; `PROJECT_PROGRESS.md`, `TEST_RESULTS.md` | Sprint 7 / 7.1–7.4 | Implementation agent |
| 2026-06-24 | — (uncommitted) | New: `domain/protocols/{transcoder,file_sender}.py`; `domain/entities/media.py` (`AudioTarget`/`AUDIO_TARGETS`); `infrastructure/downloader/ffmpeg_client.py`; `infrastructure/telegram/{client,file_sender}.py`; `services/{job_service,download_service,notification_service}.py`; `workers/{download_worker,cleanup_worker}.py`; `tests/unit/{test_job_service,test_download_service,test_notification_service,test_cleanup_worker,test_download_worker,test_format_sizes}.py`; `tests/integration/test_pipeline_repositories.py`. Updated: `core/config.py` + `.env.example` + `MASTER_PLAN.md` (`BOT_API_BASE_URL`, Section 13.2, D-040/D-041); `domain/enums/quality.py` (audio codecs); `domain/entities/media.py` (`MediaFormatOption.codec`); `domain/protocols/repositories.py` (+pipeline methods); `infrastructure/database/repositories/{job,cached_file,active_download,job_waiter,download,user}.py`; `services/{cache_service,format_extraction}.py`; `infrastructure/downloader/providers/ytdlp_provider.py`; `core/logging.py` (`get_correlation_id`); `bot/{main.py,handlers/download.py,keyboards/quality_select.py}`; `workers/main.py`; `tests/unit/{_fakes,test_download_handler,test_format_extraction,test_url_analyzer,test_bot_composition}.py`; `PROJECT_PROGRESS.md`, `TEST_RESULTS.md` | Sprint 6 / 6.1–6.10 + carry-ins | Implementation agent |
| 2026-06-23 | `a1f16ad` | New: `core/urls.py`; `domain/entities/media.py`; `domain/protocols/downloader.py`; `infrastructure/downloader/{registry,provider_settings}.py`; `infrastructure/downloader/providers/ytdlp_provider.py`; `services/{url_analyzer,format_extraction}.py`; `bot/callbacks/factory.py`; `bot/keyboards/{format_select,quality_select}.py`; `bot/handlers/download.py`; `workers/main.py`; `tests/unit/{test_urls,test_format_extraction,test_callback_factory,test_downloader_registry,test_url_analyzer,test_ytdlp_provider,test_keyboards,test_download_handler}.py`; `tests/integration/test_provider_settings.py`. Updated: `core/redis_keys.py` (+`provider_health`), `domain/protocols/repositories.py` (MediaRepositoryProtocol.upsert_metadata), `infrastructure/database/repositories/media.py` (+`upsert_metadata`), `bot/main.py`, `tests/unit/{_fakes,test_bot_composition}.py`, `.importlinter` (+providers contract), `MASTER_PLAN.md` (Section 11.4 row), `PROJECT_PROGRESS.md`, `TEST_RESULTS.md` | Sprint 5 / 5.1–5.11 | Implementation agent |
| 2026-06-23 | `0e5f301` | New: `domain/entities/user.py`; `services/{user_service,rate_limit_service}.py`; `bot/middlewares/{logging,db_session,auth,throttle}.py`; `bot/filters/role_filter.py`; `bot/handlers/{start,help}.py`; `bot/main.py`; `tests/unit/{_fakes,test_user_snapshot,test_user_service,test_rate_limit_service,test_role_filter,test_bot_middlewares,test_bot_handlers,test_bot_composition}.py`. Updated: `infrastructure/database/repositories/user.py` (+`create_user`/`touch_last_activity`), `domain/protocols/repositories.py` (UserRepositoryProtocol), `pyproject.toml` (+aiogram==3.29.0; orjson 3.11.5→3.11.6); `PROJECT_PROGRESS.md`, `TEST_RESULTS.md` | Sprint 4 / 4.1–4.9 | Implementation agent |
| 2026-06-23 | — (uncommitted) | `core/redis_keys.py`, `domain/protocols/{cache,queue}.py`, `domain/protocols/repositories.py` (SettingsStoreProtocol), `infrastructure/redis/{client,cache,locks,queue}.py`, `services/{cache_service,queue_service,settings_service}.py`, `tests/integration/{conftest,test_redis_cache,test_redis_locks,test_redis_queue,test_settings_service}.py`, `tests/unit/test_redis_keys.py`; `PROJECT_PROGRESS.md`, `TEST_RESULTS.md` | Sprint 3 / 3.1–3.7 | Implementation agent |
| 2026-06-23 | `8ccd1e6` | `alembic.ini`, `migrations/{env.py,script.py.mako,versions/2026062300{01,02}_*.py}`, `infrastructure/database/{engine,session,partitioning}.py`, `infrastructure/database/models/*.py` (13 models + base), `infrastructure/database/repositories/*.py` (12 repos + base), `domain/protocols/repositories.py`, `tests/integration/{conftest,test_schema,test_repositories,test_partition_rollover}.py`, `tests/unit/{test_partitioning,test_db_engine}.py`, `pyproject.toml` (sqlalchemy/asyncpg/alembic/redis/orjson pins); `PROJECT_PROGRESS.md`, `TEST_RESULTS.md` | Sprint 2 / 2.1–2.9 | Implementation agent |
| 2026-06-23 | `78af6ed` | `core/{config,logging,sentry,uuid7,constants,__main__}.py`, `domain/exceptions.py`, `domain/enums/{__init__,job_status,user_role,media_format,quality,error_type,ad_type}.py`, `tests/unit/test_{config,logging,sentry,uuid7,constants,enums,exceptions,main_entry}.py`, `.gitattributes`, `pyproject.toml` (sentry-sdk pin), `.env.example` (full-line comments), `MASTER_PLAN.md` (Section 9.7 `Constants` card), `PROJECT_PROGRESS.md`, `TEST_RESULTS.md` | Sprint 1 / 1.1–1.9 | Implementation agent |
| 2026-06-23 | `93524d6` | `.gitignore`, `pyproject.toml`, `mypy.ini`, `.importlinter`, `.pre-commit-config.yaml`, `.env.example`, `README.md`, `.github/workflows/ci.yml`, `deploy/docker-compose.yml`, `deploy/pgbouncer.ini`, `deploy/Dockerfile.{bot,worker,api}`, `tests/conftest.py`, 31 package `__init__.py` placeholders; `PROJECT_PROGRESS.md` + `TEST_RESULTS.md` (Sprint 0 records) | Sprint 0 / 0.1–0.10 | Implementation agent |
| 2026-06-23 | — | `MASTER_PLAN.md` (v2.1 → v2.2: Section 25 rewritten; D-031–D-039 added; Sprint 10 narrowed; Sprint 11 inserted; Sprint 11→12 renamed; DoD expanded to 19 items), `PROJECT_PROGRESS.md` (sprint structure + counts + new session handoff), `TEST_RESULTS.md` (created), `SECURITY_REPORT.md` (created), `PERFORMANCE_REPORT.md` (created) | Pre-Sprint 0 | Planning agent |
| 2026-06-23 | — | `MASTER_PLAN.md` (created, v2.0 → v2.1), `PROJECT_PROGRESS.md` (created), `database_reference.md` (marked superseded), `project_reference.md` (marked superseded) | Pre-Sprint 0 | Planning agent |

---

## Validation Status Log

Append a row whenever a validation suite runs.

| Date | Sprint / Task | Suite | Result | Notes |
|---|---|---|---|---|
| 2026-06-24 | Sprint 7 / 7.1–7.4 | Unit + Integration (290 total, live pg:15 + redis:7) + all gates | PASS | Idempotent fan-out (retry-after-partial never double-delivers), per-waiter completion notifications, one-waiter-failure isolation, history pagination + resend (cache-hit / evict+requeue / needs-relink / not-found), signed resend+page callbacks, `get_for_user` owner-scoping. mypy --strict 170 files; import-linter 7 contracts; bandit 0; pip-audit no new deps. Two schema deviations documented for Owner ratification (no `job_id`/`media_id` on `downloads`). |
| 2026-06-23 | Sprint 5 / 5.1–5.11 + 4K fix | Unit + Integration (214 total, live pg+redis) + all gates | PASS | Registry failover/health/cooldown, signed-callback tamper rejection, yt-dlp JSON parse + error mapping, COALESCE upsert verified. Post-validation 4K quality-mapping fix added with parametrized regression test; verified against the reported video (offers 2160p…144p). mypy --strict 146 files; import-linter 7 contracts; bandit 0; pip-audit no new deps. |
| 2026-06-23 | Sprint 4 / 4.1–4.9 | Unit (101) + full suite (140 incl. 39 integration) + all gates | PASS | Sprint-4 services + entity 100%, middlewares/handlers/filter 97–100%. mypy --strict 124 files; import-linter 6 contracts; bandit 0; pip-audit clean (orjson→3.11.6). |
| 2026-06-23 | Sprint 3 / 3.1–3.7 | Unit + Integration (92 tests, live redis:7 + postgres:15) + all gates | PASS | infrastructure/redis coverage 100% (≥80%). Concurrent 1000-job dequeue, lock foreign-release, read-through cache verified. |
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
| OQ-11 | Large-file delivery: accept Telegram's 50 MB bot limit, or stand up a self-hosted Telegram Bot API server (up to 2 GB)? Affects which qualities can actually be sent. | Open question | Sprint 6 | Decide before building delivery. |

Open Questions are the canonical issue board until a real one is set up. Update both this section and `MASTER_PLAN.md` Section 27 when resolving an item.

---

## Session Handoff Log

The newest handoff is at the top. Every session ends with a new entry. Never delete old entries.

### Session Handoff — 2026-06-24 — Sprint 7 Fan-Out and Resend implemented (Under Review)

| Field | Value |
|---|---|
| **Session type** | Implementation |
| **Active sprint** | 7 — **code complete, `[~]` Under Review.** Stops here for Owner human-verification + sign-off before Sprint 8. Uncommitted in worktree `happy-bose-71ed46` (branch `claude/happy-bose-71ed46`). |
| **Tasks moved** | Sprint 7 7.1–7.4 all `[x]`; Sprint 7 → `[~]` Under Review (100%). |
| **What was built** | **7.1** Duplicate requesters are attached as `job_waiters` **and** their progress message is registered in the Redis job-context `progress` map (originator seeded at job creation). **7.2** `DownloadService._deliver` delivers one file to every waiter idempotently — first undelivered waiter's upload is their delivery + mints the `file_id`; others get it via `send_cached`; the minted `file_id` + delivered `user_id`s are persisted in the Redis context so a **retry after partial delivery never double-delivers** (no re-upload, skip already-sent). Per-waiter failure is logged + skipped; **all** waiters get a ✅/❌ edit on completion/failure. **7.3** `services/history_service.py` (paginated newest-first list; resend = instant-from-cache with usage bump and no new history row, or evict+fresh-download fallback, or `NEEDS_RELINK`). **7.4** `bot/handlers/history.py` + `bot/keyboards/history.py` (`/history`, resend buttons, prev/next), new signed callback actions `r`/`h`, wired via `history_service_factory` in `bot/main.py`; `/history` added to `/help`. |
| **Validation** | **290 tests pass** (242 unit + 48 integration, live pg:15 + redis:7). ruff + ruff-format clean; mypy --strict 170 files; import-linter 7 contracts; bandit 0; pip-audit no new deps. No schema/config/dependency/migration changes. |
| **⚠ Two schema deviations needing Owner ratification (see Sprint 7 Known Issues)** | (A) `downloads` has **no `job_id`** and is partitioned, so the spec'd `(job_id,user_id)` uniqueness for idempotency is impossible — idempotency was implemented in the Redis job context instead (survives the per-job tx rollback; a DB constraint would not). (B) `downloads` has **no `media_id`**, so a genuinely NULL-`cached_file_id` resend can't be reconstructed → returns `NEEDS_RELINK`; the feasible fallback (cache row present, `file_id` rejected) reuses `cached_files.media_id` and requeues. Owner: ratify the app-layer approach, or approve a future migration adding those columns (§10/§19/§5). |
| **Remaining work** | Owner human-verification: two accounts send the same URL within seconds → both receive it once; resend from `/history` (instant when cached, fresh download when not). Then sign off Sprint 7 and authorize Sprint 8 (Admin and Ops). |
| **Known issues** | (1) Deviations A/B above. (2) Per-stage live progress bar during processing is originator-only (cosmetic); completion/failure notifies all waiters. (3) `bot.main`/`workers.main` `main()` entrypoints remain network-bound + unit-uncovered (Owner sandbox run covers them). |
| **Recommended next task** | After Owner sign-off: Sprint 8 Task 8.1 (`services/broadcast_service.py` + `workers/broadcast_worker.py`). |
| **Notes for the next agent** | Run gates with `J:/TelegramProjectNewCustomer/TelegramBot/.venv/Scripts/<tool>.exe` (ruff/mypy/lint-imports/pytest/bandit). The Redis job context (`job:{id}`) now also carries a per-waiter `progress` map, a `delivered` list, and the minted `file_id`/`unique_file_id` — `CacheService.{add_waiter_progress,record_uploaded_file,record_delivered}` own those writes. Fan-out delivery + idempotency live in `DownloadService._deliver`. `HistoryService.resend` reuses the same invalid-`file_id` eviction path as `JobService._try_deliver_cached` (both delegate eviction to the cache repo + `delete_file_id`). Bot must run from this worktree. |

### Session Handoff — 2026-06-24 — Sprint 6 Completed (Owner sign-off, committed) → start Sprint 7

| Field | Value |
|---|---|
| **Session type** | Implementation + Owner live testing + fixes |
| **Active sprint** | 6 — **`[x]` Completed**, Owner sign-off 2026-06-24, committed `ec0ac7f` on `claude/happy-bose-71ed46`. **Next session: start Sprint 7 (Fan-Out and Resend).** |
| **Commit** | `ec0ac7f` — "Sprint 6: end-to-end job pipeline + Owner live-test fixes" (53 files). Tree clean. |
| **What works (Owner-confirmed)** | URL → instant "Analyzing…" ack → thumbnail + title/duration/source → format → quality (with ⬅️ Back) → single progress bar → **one** delivered file named after the title. Videos play inline (mp4); audio in all codecs (mp3/m4a/aac/ogg/opus/wav/flac); TikTok/Instagram/YouTube tested. Cache-hit instant resend; **self-healing** when a cached file_id is invalid (bot/endpoint change). |
| **Validation** | 268 tests (222 unit + 46 integration). ruff, mypy --strict (165 files), import-linter (7 contracts), bandit (0), pip-audit (no new deps). Note: Sprint-3 Redis concurrency tests (`test_redis_queue.py`) are occasionally flaky under parallel load — they pass in isolation; not a regression. |
| **Sprint 7 scope (next)** | 7.1 `JobService.request` already inserts `job_waiters` on the duplicate path (done in S6) — verify/extend. 7.2 `DownloadService._deliver` already loops all waiters + uploads to the first, send_cached to the rest — extend with per-waiter progress messages (each waiter has their own progress message_id; today only the originator's is tracked in the Redis `job:{id}` context). 7.3 `services/history_service.py` (paginated read from `downloads`, resend via cached `file_id` → flow 16.3, reuse the self-healing path). 7.4 `bot/handlers/history.py` + `bot/keyboards/history.py`. See the Owner's richer **History UI** note in the Sprint 7 section (browse title/thumbnail/platform/date) — may be its own sprint. |
| **Key implementation notes for Sprint 7** | Fan-out per-waiter progress needs each waiter's `(telegram_id, message_id)` — extend the Redis job context (`CacheService.set_job_context`) from a single originator blob to a per-waiter list, or store a waiter→message map. `DownloadService._deliver` is where multi-recipient delivery lives. `HistoryService` resends should go through the same invalid-file-id eviction path as `JobService._try_deliver_cached` (factor it out if shared). Run gates with `J:/TelegramProjectNewCustomer/TelegramBot/.venv/Scripts/<tool>.exe`. Bot must run from this worktree. |

### Session Handoff — 2026-06-24 — Sprint 6 Job Pipeline implemented (Under Review)

| Field | Value |
|---|---|
| **Session type** | Implementation |
| **Active sprint** | 6 — **code complete, `[~]` Under Review.** Stops here for Owner human-verification + sign-off before Sprint 7. |
| **Tasks moved** | Sprint 6 6.1–6.10 all `[x]`; all four Owner carry-ins delivered. Sprint 6 → `[~]` Under Review. |
| **Files modified** | See the 2026-06-24 row in the Files Modified Log (uncommitted in worktree `happy-bose-71ed46`). |
| **Decisions added** | **D-040** (self-hosted Bot API server, 2 GB; new `BOT_API_BASE_URL` env var in Section 13.2 — resolves OQ-11). **D-041** (per-codec audio modeled via `Quality` audio members + `MediaFormatOption.codec`, reusing the locked `(media_id, format, quality)` cache key). |
| **Validation** | 243 tests pass (197 unit + 46 integration, incl. a new live-DB `test_pipeline_repositories`). ruff/mypy --strict (163 files)/import-linter (7 contracts)/bandit/pip-audit all green. A live-DB test caught + fixed a stale-identity-map bug in `CachedFileRepository.upsert` (`populate_existing=True`). |
| **Current state** | Full pipeline is built: pick a quality → progress message → worker downloads via the registry, transcodes audio targets via FFmpeg, uploads once to the storage chat to mint a `file_id`, caches it, delivers to the user, and edits the message through the stages to ✅/❌. Cache hits deliver instantly. Thumbnails show on the format message; audio offers explicit codecs; video sizes include audio. **Not yet run end-to-end against a live bot** (that is the Owner verification step). |
| **Completed work** | All Sprint 6 tasks + carry-ins. Governance: `BOT_API_BASE_URL`, D-040, D-041. |
| **Remaining work** | Owner human-verification (live bot + worker). Then Sprint 7 (fan-out delivery to all waiters + per-waiter progress; `HistoryService` + history handlers). |
| **Known issues** | (1) `tenacity` deferred (not vendored) — job-level retry implemented instead, which is the validated behavior. (2) Fan-out is single-user only until Sprint 7. (3) `main()` entrypoints unit-uncovered (need a live token). (4) Per-codec audio size estimates are approximate (`~`). |
| **Recommended next task** | Owner: run `python -m bot.main` and `python -m workers.main` (or the deploy containers) with a test bot token, `BOT_API_BASE_URL` pointed at a self-hosted Bot API server, `yt-dlp`/`ffmpeg` installed, and the migrated test DB + Redis up. Send a URL, confirm progress + file; resend, confirm instant cache; try an audio codec. Then sign off Sprint 6 and authorize Sprint 7. |
| **Notes for the next agent** | Run gates with `J:/TelegramProjectNewCustomer/TelegramBot/.venv/Scripts/<tool>.exe` (ruff/mypy/lint-imports/pytest/bandit). The worker process is the only place files are uploaded/delivered — it builds a per-job `DownloadService` via `make_download_service_factory` in `workers/main.py`. The worker reads progress context (telegram_id, message_id, lock token) from Redis key `job:{id}` written by `JobService.request`; the lock is acquired in the bot process and released by the worker. `FileSenderProtocol.upload` targets `bot_owner_telegram_id` as the storage chat. Self-hosted Bot API is selected by `build_bot` in `infrastructure/telegram/client.py` when `BOT_API_BASE_URL` is set. |

### Session Handoff — 2026-06-23 — Sprint 5 committed + owner validation (4K fix); ready for Sprint 6

| Field | Value |
|---|---|
| **Session type** | Implementation + owner validation |
| **Active sprint** | 5 → **Completed (Owner sign-off 2026-06-23, `a1f16ad`)**. **Next session: start Sprint 6.** |
| **Tasks moved** | Sprint 5 5.1–5.11 all `[x]`; Sprint 5 → `[x]` Completed (Owner sign-off 2026-06-23). |
| **Files modified** | Sprint 5 committed in `a1f16ad` (see Files Modified Log). This session also: fixed `_quality_for_format` in `infrastructure/downloader/providers/ytdlp_provider.py` + regression test in `tests/unit/test_ytdlp_provider.py`; doc updates in `PROJECT_PROGRESS.md`. |
| **Decisions added** | None to MASTER_PLAN. Added OQ-11 (50 MB bot limit vs self-hosted Bot API server) — must be decided before Sprint 6 large-file delivery. |
| **Validation** | 214 tests pass; all gates green. Owner hand-tested live YouTube/TikTok/etc.: analysis + format→quality keyboards work; cache speed-up confirmed; rejection of bad/non-URLs confirmed. |
| **Current state** | The full URL→analysis→format/quality-selection UX is live and committed. The quality menu now correctly shows 4K for non-16:9 videos. Selecting a quality ends at a "Downloading will be available soon" placeholder — the actual download engine is Sprint 6 (not built). |
| **Completed work** | Sprint 5 (provider abstraction, URL analyzer, keyboards, signed callbacks, worker health task, import contract). Post-validation 4K quality-label fix. |
| **Remaining work** | Sprint 6 (Job Pipeline) — see its task list **and the "Owner-requested carry-ins for Sprint 6"** block: real download/transcode/upload + delivery, progress feedback, thumbnail preview, accurate size estimates, explicit per-codec audio formats. |
| **Known issues** | (1) File-size labels rough / non-monotonic (cosmetic; fix in Sprint 6 download path). (2) Audio shown as a single "Audio" option (explicit codecs need FFmpeg + a model change → Sprint 6). (3) `bot.main`/`workers.main` entrypoints not unit-tested (covered by the live run). |
| **Recommended next task** | Sprint 6 Task 6.1 (`domain/protocols/transcoder.py`, `domain/protocols/file_sender.py`). First confirm OQ-11 (file-size/Bot-API decision) with the Owner. |
| **Notes for the next agent** | To run/validate the bot you need `yt-dlp` installed and `YTDLP_PATH` set in the worktree `.env` (it's a subprocessed system tool, not a pyproject dep). Run gates with `J:/TelegramProjectNewCustomer/TelegramBot/.venv/Scripts/<tool>.exe`. The download quality-pick handler in `bot/handlers/download.py` (`handle_quality_choice`) is the placeholder to replace in Task 6.8 (it currently just edits the message). Provider settings are read by the registry via `ProviderSettingsAdapter` (opens its own short session); the registry is a process singleton built in both `bot/main.py` and `workers/main.py`. |

### Session Handoff — 2026-06-23 — Sprint 5 URL Analyzer + Provider Abstraction implemented

| Field | Value |
|---|---|
| **Session type** | Implementation |
| **Active sprint** | 5 (URL Analyzer + Provider Abstraction) — STOP for Owner review |
| **Tasks moved** | Sprint 4 → `[x]` Completed (Owner sign-off; committed `0e5f301`). Sprint 5 tasks 5.1–5.11 all `[x]`; Sprint 5 → `[~]` Under Review (100%). |
| **Files modified** | See the Sprint 5 / 5.1–5.11 row in the Files Modified Log. |
| **Decisions added** | None. No new dependencies (yt-dlp is a subprocess binary, not a Python import). No schema/migration changes; provider settings were already seeded in Sprint 2. Provider control-flow exceptions + `ProviderSettingsProtocol` are additive (Section 9.4 "add new protocols/types"). Added `provider:health:{name}` to the Section 11.4 key table. |
| **Validation** | 208 tests (168 unit + 40 integration vs live pg:15 + redis:7). All gates green: ruff, ruff-format, mypy --strict (146 files), import-linter (7 contracts incl. new `providers-only-via-registry`), bandit (0), pip-audit (no new deps). |
| **Current state** | The full provider abstraction is in place (D-026/D-029): services see only `DownloaderProtocol`; `DownloaderRegistry` owns selection, failover, and health. `YtdlpProvider` is the sole registered provider, wrapping the `yt-dlp` binary as a subprocess. `URLAnalyzerService` turns a URL into an `AnalyzedMedia` (cache-first metadata). The bot shows a format keyboard then a quality keyboard via HMAC-signed callbacks. The worker process runs the periodic health-check task. import-linter forbids any provider import outside the registry/composition-roots. |
| **Completed work** | Tasks 5.1–5.11. Resolved during the run: (1) `DownloaderProtocol` attrs were initially `ClassVar` (RUF012 fix) but that blocked per-instance test fakes — reverted to instance attributes set in `__init__`; (2) the registry is a process singleton but provider settings are per-DB — solved with `ProviderSettingsAdapter` (infrastructure) opening short-lived sessions, injected via the domain `ProviderSettingsProtocol`; (3) bandit's Windows txt formatter crashed on a `⇒` in an `assert` comment — replaced the `assert` with an explicit guard (also removes a B101 finding); (4) `(platform, video_id)` for the DB/cache key is URL-derived so the pre-extraction lookup and post-extraction upsert address the same row. |
| **Remaining work** | Owner review of Sprint 5 (hand-test 5 URLs/platform — needs a real bot + yt-dlp installed). Then Sprint 6 (Job Pipeline: `JobService`, `DownloadService`, `DownloadWorker`, `TelegramFileSender`; wires the quality-pick callback to `JobService.request`). |
| **Known issues** | OQ-8 (platform allowlist) / OQ-9 (yt-dlp cadence) still open — V1 lets yt-dlp decide. Composition-root `main()` entrypoints aren't unit-tested (need live token/infra). |
| **Recommended next task** | After Owner sign-off: Sprint 6 Task 6.1 (`domain/protocols/transcoder.py`, `file_sender.py`). |
| **Notes for the next agent** | Never import a provider outside `infrastructure/downloader/providers/` + the composition roots (import-linter enforces it). The quality-pick handler in `bot/handlers/download.py` is the Sprint 6 hook point for `JobService.request` (currently a placeholder acknowledgement). `URLAnalyzerService.analyze` returns `AnalyzedMedia(media_id, info)`; callbacks carry `media_id` and re-resolve via `analyze_by_media_id`. The registry reads provider settings through `ProviderSettingsAdapter` (opens its own sessions); it only runs on a metadata-cache miss. yt-dlp must be installed on the worker/bot host for real extraction (the Owner's host already has it for the bot run). |

### Session Handoff — 2026-06-23 — Sprint 4 User Identity implemented

| Field | Value |
|---|---|
| **Session type** | Implementation |
| **Active sprint** | 4 (User Identity) — STOP for Owner review |
| **Tasks moved** | Sprint 3 → `[x]` Completed (Owner pre-authorized continuation). Sprint 4 tasks 4.1–4.9 all `[x]`; Sprint 4 → `[~]` Under Review (100%). |
| **Files modified** | New: `domain/entities/user.py`; `services/{user_service,rate_limit_service}.py`; 4 bot middlewares; `bot/filters/role_filter.py`; `bot/handlers/{start,help}.py`; `bot/main.py`; 8 unit-test modules (incl. `tests/unit/_fakes.py`). Updated: `infrastructure/database/repositories/user.py`, `domain/protocols/repositories.py`, `pyproject.toml`, `PROJECT_PROGRESS.md`, `TEST_RESULTS.md`. |
| **Decisions added** | None. aiogram==3.29.0 added (pre-approved in Section 6.1 — first sprint to use the Telegram framework). orjson patch-bumped 3.11.5→3.11.6 to clear advisory GHSA-hx9q-6w63-j58v (already-approved dep; no new decision needed). |
| **Validation** | 101 unit tests (48 new); full suite 140 pass (101 unit + 39 integration, live redis:7 + postgres:15). Sprint-4 services + entity 100% coverage; middlewares/handlers/filter 97–100%. All gates: ruff, ruff-format, mypy --strict (124 files), import-linter (6 contracts), bandit (0), pip-audit (clean). |
| **Current state** | The full auth/throttle pipeline is in place: `logging → db_session → auth → throttle → handler`. `UserService` is cache-first (D-014) with debounced activity writes and audit-preserving ban/unban; `RateLimitService` covers message throttle + the Section 16.5 download checks (lazy daily reset, effective-plan resolution, cooldown). Services stay framework-agnostic (`import-linter` green); `bot/main.py` is the sole composition root reaching infrastructure. Long-polling is the default run mode; webhook is wired but optional. |
| **Completed work** | Tasks 4.1–4.9. Resolved during the run: (1) services may not import the ORM model, so `UserService` builds `UserSnapshot` from repo rows by attribute access and the repo gained `create_user`/`touch_last_activity`; (2) `Settings()` no-arg constructor needs `# type: ignore[call-arg]` (pydantic-settings reads env, mypy can't see it); (3) `AsyncMock(spec=Message)` doesn't auto-async `answer` — tests set `event.answer = AsyncMock()`; (4) orjson advisory cleared by patch bump. |
| **Remaining work** | Owner review of Sprint 4 (human verification: run the sandbox bot, `/start` owner→owner role, second account→user role, ban/unban via SQL). Then Sprint 5 (URL Analyzer + Provider Abstraction). |
| **Known issues** | `bot/main.py` `main()`/`_run_webhook` are not unit-tested (need a live token + infra); covered by the Owner bot run. (Debounce was tightened 60 s → 5 s per Owner direction.) |
| **Recommended next task** | After Owner sign-off: Sprint 5 Task 5.1 (`domain/protocols/downloader.py`). |
| **Notes for the next agent** | Per-update services are built from factories bound to `data["session"]` (set by `DbSessionMiddleware`, which must precede `auth`/`throttle`). `auth`/`throttle` attach to `dp.message`/`dp.callback_query` (they need `event_from_user`); `logging`/`db_session` are `dp.update` outer middlewares. `UserSnapshot` is the framework-free user view crossing the service→bot boundary and the value cached in Redis — build it via `UserSnapshot.from_row(...)` / round-trip via `to_cache_dict`/`from_cache_dict`. Rate-limit keys (`rate:msg:*`, `rate:dl_cooldown:*`) use the internal `users.id`, not `telegram_id`. Run gates with `J:/TelegramProjectNewCustomer/TelegramBot/.venv/Scripts/<tool>.exe`. |

### Session Handoff — 2026-06-23 — Sprint 3 Cache and Queue implemented

| Field | Value |
|---|---|
| **Session type** | Implementation |
| **Active sprint** | 3 (Cache and Queue) — STOP for combined Owner review of Sprints 2 + 3 |
| **Tasks moved** | Sprint 2 → `[x]` Completed. Sprint 3 tasks 3.1–3.7 all `[x]`; Sprint 3 → `[~]` Under Review (100%). |
| **Files modified** | New: `core/redis_keys.py`; `domain/protocols/{cache,queue}.py`; `infrastructure/redis/{client,cache,locks,queue}.py`; `services/{cache_service,queue_service,settings_service}.py`; 5 integration test modules + `tests/unit/test_redis_keys.py`. Updated: `domain/protocols/repositories.py` (added `SettingsStoreProtocol`); `PROJECT_PROGRESS.md`, `TEST_RESULTS.md`. |
| **Decisions added** | None. No new dependencies (redis/hiredis/orjson were added in Sprint 2). |
| **Validation** | 92 tests pass (53 unit, 39 integration) against live redis:7 + postgres:15. `infrastructure/redis` coverage 100%; services 92–100%. All gates: ruff, ruff-format, mypy --strict (105 files), import-linter (6 contracts), bandit (0), pip-audit (clean). |
| **Current state** | Every Redis interaction flows through the LOCKED Section 11.4 key scheme (one helper per key in `core/redis_keys.py`). Typed `CacheService` (no raw keys), token-tagged distributed `RedisLock`, Lua-atomic priority `RedisQueue`, and a read-through/write-through `SettingsService`. Full infra stack (postgres/redis/pgbouncer/uptime-kuma) is up. |
| **Completed work** | Tasks 3.1–3.7. Resolved during the run: (1) redis-py async methods are typed `Awaitable[T] | T` → targeted `# type: ignore[misc]`/`[no-untyped-call]` in the adapters; (2) `Setting.value` is `Mapped[str]`, not `str`, so it can't structurally match a `value: str` protocol attribute → `SettingsStoreProtocol` returns `Any`; (3) Docker Desktop daemon dropped twice mid-session → restarted; integration suites auto-skip when Redis/DB are down. |
| **Remaining work** | Owner review of Sprints 2 + 3, then Sprint 4 (User Identity: UserService, RateLimitService, bot middlewares, start/help handlers, `bot/main.py` composition root). |
| **Known issues** | Build-host Docker Desktop is flaky; not a code issue. |
| **Recommended next task** | After Owner sign-off: Sprint 4 Task 4.1 (`services/user_service.py`). |
| **Notes for the next agent** | Build Redis keys ONLY via `core.redis_keys.RedisKeys` — never inline strings. `CacheService` exposes typed methods (`get_file_id`, `get_user`, `acquire_download_lock`, …); callers never pass raw keys. `QueueService.enqueue(job_id, priority=…)` scores via Section 12.2 (lower = sooner); dequeue is Lua-atomic and moves the member to `queue:active` (call `ack` when done). `SettingsService.get` returns the typed value cast from `value_type`; `set` writes through and invalidates. CI must start both postgres and redis service containers and run `alembic upgrade head` before integration tests. |

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
