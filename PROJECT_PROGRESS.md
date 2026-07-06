# Project Progress Tracking

> **Document Status:** LIVE · Single Source of Truth for implementation status
> **Companion Documents:** `MASTER_PLAN.md` (architecture, sprint plan, locked decisions), `TEST_RESULTS.md`, `SECURITY_REPORT.md`, `PERFORMANCE_REPORT.md`
> **Last Updated:** 2026-07-05 (Sprint 13 Admin Panel Enhancement and Growth Features — implemented, awaiting Owner sign-off)
> **Project Phase:** Sprint 13 (Admin Panel Enhancement and Growth Features) **Implemented** (9/9), not yet pushed. Sprint 12 Phase A remainder (A2–A6) and Phase B still pending Owner infra; S9/S9.5/S10/S11 Phase B sign-offs also pending. See **Current Project State** below for the full picture — this banner was stale since Sprint 6 and is corrected here per this file's own drift rule.
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
| Master Plan version | v2.2 (+ D-040, D-041, D-049, D-050, ..., D-061–D-064; `BOT_API_BASE_URL` env var; `DEFAULT_LOCALE` env var) |
| Current sprint | **Sprint 13 — Admin Panel Enhancement and Growth Features IMPLEMENTED (2026-07-05).** All 9 tasks (13.1–13.9) done: `bot/panel/ui.py` "Dashboard Grade" design system + animation-ready emoji layer; per-platform download analytics + CSV export; enhanced user-activity metrics (24h/7d/30d active, 5d/7d/30d inactive, hourly); blocked-bot/deleted-account detection + on-demand health sweep + purge; subscriber export/import (CSV/JSON, create-only); full referral system (deep-link, rewards, admin dashboard); admin-editable message templates (transparent `core.i18n` override); main-menu live dashboard + Statistics/User-detail/Downloads/System screens redesigned through the new design system; registry/FSM/composition-root wiring for all of the above. 18 feature commits (`cecc297`..`3e90c8d`) + 1 chore (`0c523d3`, untrack accidental `graphify-out/` artifacts), all on `claude/happy-bose-71ed46`, **not pushed**. — Before this: **Sprint 11.5 — Internationalization (i18n) IMPLEMENTED (2026-07-01)**, inserted between Sprint 11 and Sprint 12. Pulled forward from V2 at Owner direction — see full detail below. All 12 tasks (11.5.1–11.5.12) done: English + Arabic catalogs, `core/i18n.py`, `users.language` as the single locale field (no migration), button-only language change (no gate, no command), full handler/keyboard/admin-panel migration, new `test_i18n.py`. — Before this: **Sprint 12 — Launch Readiness STARTED (2026-07-01).** Phase A/B split approved; **A1 done** (`deploy/docker-compose.prod.yml`, `d06b583`). Phase A remainder (A2–A6) not started; Phase B blocked on Owner infra + OQ-1/3/5 + Sprint 11 Phase B. Alongside A1, an Owner-requested admin-panel batch shipped + **pushed**: user-management action fixes (`8542e2d`, **Owner req #10**) + Statistics enrichment (`4d675cb`). — Earlier: **Sprint 11 Phase A ✅ COMPLETE** (11.1–11.9, pushed `6e88739`, **Gate G-5 ✅ 2026-06-27**); Phase B (11.10–11.14) ⏳ waiting for sandbox bot + test infra. Deferred-backlog (8.3/9.5.9/9.5.10) done; Sprint 9 + 9.5 + 10 still `[~]` Under Review. |
| Sprints completed | 8 / 13 signed off (S0–S8; 8.3 HTTP API now implemented, `[~]` Under Review). S9 under review; **S9.5 now 10/10 implemented** (`[~]` Under Review); S10 under review; **S11 Phase A 9/14 done** (Phase B infra-blocked); **S11.5 (decimal, like S9.5) 12/12 implemented**, human-verification parked for Phase B alongside S11's; **S13 (new numbered sprint, out of original order — see note below) now 9/9 implemented**, `[~]` Under Review, awaiting Owner sign-off + push decision. |
| Tasks completed | 95 / 105 (S0–S6 = 65; S7: 4/4; S8: **3/3**; S9: 4/4; S10: 8/8 — S8.3/S9/S10 under review; **S11: 9/14** — Phase A 11.1–11.9 done, Phase B 11.10–11.14 infra-blocked) + Owner-feedback hardening rounds #14–#31. **Decimal sub-sprints and Sprint 13 tracked separately, not in this 105 fixed denominator** (matching the S9.5 precedent): S9.5 **10/10**; S11.5 **12/12**; **S13 9/9 (new, 2026-07-05)**. |
| Open blockers | 0 |
| Open decisions awaiting Owner | 8 OQs (**OQ-10 resolved 2026-07-01** — Sprint 11.5 shipped EN+AR, copy specified directly by the Owner's own design session) + ratify documented deviations (BroadcastWorker polling vs §16.8; `downloads` has no `job_id`/`media_id`). Task 8.3 `ADMIN_API_KEY` reconciliation RESOLVED (D-051); **8.3 Owner-signed-off 2026-06-26**. Sprint 9 / 9.5 / 10 sign-offs pending; Sprint 11.5's live-bot human-verification walkthrough parked for Sprint 11 Phase B (needs the sandbox bot). **New:** Sprint 13 sign-off pending (code/tests complete, not yet reviewed live); animated-emoji requires the Owner to obtain a Fragment-purchased bot username + supply `custom_emoji_id`s before `bot/panel/ui.py`'s `CUSTOM_EMOJI_IDS` map can be filled in — until then all panel icons render as plain Unicode by design (Telegram Bot API restriction, not a bug). |
| Last code change | 2026-07-05 — **Sprint 13, this session:** see the new Sprint 13 detail section below for the full breakdown (design system, 6 features backend+front-end, 5 screens redesigned, full registry/FSM/composition wiring). 3 new Alembic migrations (`202607050001`–`202607050003`, head now `202607050003`). — Earlier: 2026-07-01 Sprint 11.5 (i18n): `core/i18n.py` (catalog loader) + `core/locales/{en,ar}.json` (~250+ keys each) + `Settings.default_locale`; `UserFacingError.translation_key`; `UserService.set_language`; `AuthMiddleware` default-locale seeding + new `LocaleMiddleware`; composition-root wiring (`bot/main.py`, `workers/main.py`); `bot/keyboards/language_select.py` + signed `l` callback action + both entry points (`/start` button, admin-panel Language section); `NotificationService` + fan-out per-recipient locale threading; full migration of `bot/handlers/{start,help,download,history,admin,ads,admin_panel,admin_wizard}.py`, `bot/keyboards/{format_select,quality_select,history,admin_panel}.py`, `bot/panel/registry.py`; new `tests/unit/test_i18n.py` (22 tests) + every touched test file updated. — Earlier same day: admin-panel batch (`8542e2d`, `4d675cb`) + `deploy/docker-compose.prod.yml` (`d06b583`, Sprint 12 A1). |
| Last documentation change | 2026-07-05 — **This session:** this file (Current State, Sprint Overview, new Sprint 13 detail section, Session Handoff). — Earlier: 2026-07-01 `MASTER_PLAN.md` (new §23 "Sprint 11.5" section; D-061–D-064; §2.4/§3/§9/§10.2/§10.13/§13.2/§17/§18/§25.7.1/§27 updated); `project_reference.md` (§23.2/§23.3 rewritten from the stale "Future/P1" sketch to the as-built design; §10.13/§12.3-area notes corrected). |
| Next recommended action | **Owner reviews Sprint 13** (SPRINT_13_PLAN.md scope, the 19 commits on `claude/happy-bose-71ed46`, and — most usefully — runs the live bot; `alembic upgrade head` is already applied to the dev DB) and decides: (a) sign off, (b) request the residual 13.2 cosmetic polish (user-list rows, moderation banned list, errors/jobs, ads list/detail, settings grouping, broadcast screen still pre-redesign formatting — all functional), (c) push the branch. Separately, still pending from before Sprint 13: **Sprint 12 Phase A remainder** (A2 `.env.production.example` → A3 smoke-test scripts/checklist → A4 release checklist → A5 CI release wiring → A6 runbook drift fix — note the migration head has since moved to `202607050003`). **Phase B blocked** on Owner provisioning production infra + answering **OQ-1** (Sentry) / **OQ-3** (host) / **OQ-5** (alerts chat), and transitively on **Sprint 11 Phase B** (which now also carries Sprint 11.5's live-bot language-change verification). Also pending: Owner req **#11** (verify daily-limit auto-reset); S9/S9.5/S10 sign-offs. |

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
| 7 | Fan-Out and Resend | `[x]` Completed | 100% | 4 / 4 | Owner sign-off 2026-06-24 (`7b18b7f`) |
| 8 | Admin and Ops | `[x]` Completed | 100% | 3 / 3 | 8.1/8.2 Owner sign-off 2026-06-24 (`df530a8`); **8.3 HTTP API Owner sign-off 2026-06-26** (live-tested via curl + D-054 unban fix) |
| 9 | Smart Advertisements | `[~]` Under Review | 100% | 4 / 4 | code complete; awaiting Owner sign-off |
| 9.5 | Ads v2 (Advertisements expansion) | `[~]` Under Review | 100% | 10 / 10 | 9.5.1–9.5.10 built + tested (9.5.9 ad_events + 9.5.10 scheduling done 2026-06-25); awaiting Owner sign-off |
| 10 | Observability and Backup | `[~]` Under Review | 100% | 8 / 8 | code/ops complete; awaiting Owner sign-off |
| 11 | Testing Framework, Security, Load and Stress | `[~]` Phase A Complete | 64% | 9 / 14 | Phase A done + Gate G-5 ✅ 2026-06-27; Phase B (11.10–11.14) blocked on Owner sandbox-bot + test infra |
| 11.5 | Internationalization (i18n) — *decimal, like 9.5, not in Total below* | `[~]` Implemented | 100% | 12 / 12 | code/tests complete 2026-07-01; live-bot human-verification parked for Sprint 11 Phase B |
| 12 | Launch Readiness | `[ ]` Not Started (original 12.1–12.7) | 0% | 0 / 7 | The original 7 tasks (≈ new "Phase B": deploy, Sentry/Kuma, smoke tests, ...) are unstarted, depend on S11 Phase B + Owner infra. A separate, **not-in-this-count** Phase A prep layer (A1–A6) started: **A1 done** (`deploy/docker-compose.prod.yml`, `d06b583`); A2–A6 not started. |
| 13 | Admin Panel Enhancement and Growth Features | `[~]` Implemented (2026-07-05) | 100% | 9 / 9 | 13.1–13.9 all implemented and gated (backend + front-end for every task); awaiting Owner sign-off + a decision on pushing `claude/happy-bose-71ed46`. Not yet folded into the fixed 105-task total below (new sprint, same convention as 9.5/11.5 until the Owner ratifies where it counts). |
| **Total** |  |  | **90%** | **95 / 105** | Row sum above is 93; **+2** from Owner-feedback hardening rounds #14–#31 (not broken out as their own row, longstanding convention). Excludes decimal sub-sprints 9.5 (10/10) and 11.5 (12/12), and Sprint 13 (9/9, tracked in its own row above) — tracked separately, per precedent. |

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
| **Status** | `[x]` Completed (Owner sign-off 2026-06-24, committed `7b18b7f`; live-verified across fan-out + history resend) |
| **Completion** | 100% (4 / 4) |
| **Goal** | Two users requesting the same content while a download is in flight both receive the file. Resend from history works. |
| **Stop Point** | Owner: two human accounts request same URL → both receive. Resend from history works. |

**Completed Tasks**

- [x] **7.1** `JobService.request` duplicate path attaches the user as a `job_waiters` row (16.4) **and** registers their progress message in the Redis job context (`progress` map) so the worker edits *their* message to ✅/❌, not only the originator's. The originator is seeded into the same map at job creation.
- [x] **7.2** `DownloadService._deliver` reads every waiter and delivers once to each — the first not-yet-delivered waiter's upload is their delivery (mints the `file_id`), every other waiter gets that `file_id` via `send_cached`. **Idempotent across retries:** the minted `file_id` and the set of already-delivered `user_id`s are persisted in the Redis job context (outside the per-job DB transaction), so a retry after a partial delivery reuses the `file_id` (no re-upload → the first waiter is never re-delivered) and skips `send_cached` for anyone already delivered. `downloads` rows + counters are re-created for every waiter (they rolled back). One waiter's delivery failure is logged and skipped (risk-table mitigation), never blocking the rest. On completion/failure **all** waiters' progress messages are edited.
- [x] **7.3** `services/history_service.py` — paginated newest-first read (`HISTORY_PAGE_SIZE=5`, over-reads by one to detect the next page) and `resend`: deliver instantly from cache (bump `usage_count`, **no** new `downloads` row, 16.3 step 5); on a Telegram-rejected `file_id` evict the stale cache and fall back to a fresh `JobService.request` (16.3 step 4); on an unreconstructable row return `NEEDS_RELINK`.
- [x] **7.4** `bot/handlers/history.py` (`/history`, page nav, resend) + `bot/keyboards/history.py` (resend button per row + prev/next), wired via a new `history_service_factory` in `bot/main.py`. New signed callback actions `r` (resend `download_id`) and `h` (history page). `/history` added to `/help`.

**Owner-requested History UX (future enhancement — 2026-06-24, do NOT implement before its sprint):** a History section where the user browses previously downloaded media with **title, thumbnail, platform, and date**; tapping an entry **instantly re-sends** it. Sprint 7's 7.3/7.4 deliver the **resend mechanics + a basic list** (platform/quality/format/date, newest first); the richer browsable UI (thumbnails + titles) is the Owner's desired surface and may warrant its own dedicated sprint. NOTE: `downloads` (§10.5) carries no `title`/`thumbnail`/`media_id` columns — a thumbnail/title grid would read those from `media_metadata`, which needs a join key (`media_id`) the history row does not store. Flag for the dedicated History-UI sprint.

**Owner History requirements added during verification (2026-06-24, items #25–#27 — core requirements for the History sprint, NOT yet implemented):**
- **#26 — show the media title, not the platform.** The list must display the actual video/song/media **title** as the primary label (e.g. "Song Name", "Video Title"), never "YouTube"/"TikTok". Date is not needed in the main list; sort by **most-recently downloaded/opened, newest at top**. The current Sprint-7 list shows platform/quality because `downloads` has no `title` — this needs a `title` column on `downloads` (or a `media_id` join to `media_metadata`). **Schema change → its own sprint.**
- **#25 — deduplicate history.** Re-downloading the exact same `(source URL / media_id, quality, format)` must **not** create a duplicate history row — reuse/update the existing record so the list stays clean. Needs a uniqueness key on `downloads` (e.g. `(user_id, media_id, format, quality)`) which today does not exist (no `media_id`; partitioned table) — **schema change → its own sprint.**
- **#27 — instant file_id delivery (ALREADY met by the resend mechanics).** History playback must reuse the stored Telegram `file_id`, never re-download / re-run yt-dlp / use the queue. `HistoryService.resend` already does exactly this (sends `cached_files.telegram_file_id` first; only falls back to a fresh download if Telegram rejects the id). Keep this as a locked requirement when the richer UI is built.

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
| **Status** | `[x]` Completed (8.1/8.2 Owner sign-off 2026-06-24, committed `df530a8`, incl. feedback rounds #14–#27). **8.3 HTTP API Owner sign-off 2026-06-26** (live-tested via curl; D-054 unban fix applied). |
| **Completion** | 100% (3 / 3 — 8.3 implemented 2026-06-25; Owner sign-off pending) |
| **Goal** | Owner and Moderator administer the bot from within Telegram. |
| **Stop Point** | Owner runs every admin command and sends a broadcast. |

**Completed Tasks**

- [x] **8.1** `services/broadcast_service.py` + `workers/broadcast_worker.py`. `BroadcastService.create` snapshots the matching, non-banned audience size into `broadcasts.expected_total` and inserts a `pending` row (16.8 step 1). `BroadcastWorker` **polls** the durable `broadcasts` table for the oldest `pending` row, marks it `in_progress`, and fans it out in id-cursor chunks of `broadcast_chunk_size`: per chunk it reads a page, sends each message (no session held during network I/O), then commits the `total_sent`/`total_failed` deltas in their own transaction (so progress survives a crash). One recipient's failure is logged + counted, never aborting; on completion → `completed` + `completed_at`. New repo SQL: `UserRepository.{count_all,count_banned,sum_total_downloads,count_for_broadcast,page_for_broadcast}` and `BroadcastRepository.{create_pending,get_next_pending,set_status,add_counts}`.
- [x] **8.2** `bot/handlers/admin.py` — `/stats` (user totals + queue depth, staff), `/userinfo <id>` (staff), `/ban <id> [reason]` / `/unban <id>` (owner), `/settings` (staff) / `/setting_set <key> <value>` (owner, validates value against the key's `value_type`, rejects unknown keys — the §13.4 set is LOCKED), `/broadcast <text> [--lang xx] [--role xx]` (owner). Authorization is declarative via `RoleFilter` (`StaffFilter` = owner|moderator; `OwnerFilter` = owner) per the §9.1 "authz never in handlers" rule; a trailing catch-all replies "not permitted" when a role-gated handler declines. Service additions: `UserService.{get_stats,find}`, `SettingsService.{list_all,set_validated}` (+`InvalidSettingValueError`).
- [x] **8.3** `/v1/admin/*` HTTP API — **IMPLEMENTED 2026-06-25** (deferred-backlog session; `[~]` Under Review pending Owner sign-off). All 11 §20.2 endpoints on the existing Sprint-10 FastAPI process: `GET /v1/admin/{stats,users,users/{id},jobs,queue,errors,settings}`, `POST /v1/admin/users/{id}/{ban,unban}`, `PUT /v1/admin/settings/{key}`. Gated by the new `ADMIN_API_KEY` env var (added to the LOCKED §13.2 set, **D-051**, resolving the §13.2-vs-§20.3 conflict — Owner-approved); `X-API-Key` header, constant-time compare. **Key unset → router not mounted (paths 404, "silently ignored"); key set → missing/wrong key 401.** Routes carry no business logic (§1.5.1) — they delegate to `UserService`, `SettingsService`, `QueueService`, and the new lightweight `AdminService` (jobs listing + error-log browse). `api/routes/admin.py` imports services/domain/core only (import-linter clean); `api/main.py` wires concretes. Files: `api/routes/admin.py`, `services/admin_service.py`, `core/config.py` (+`admin_api_enabled`), `infrastructure/database/repositories/{job,error_log}.py` (`list_recent`), `services/settings_service.py` (`get_view`), `api/app.py`/`api/main.py`, `.env.example`. **Validation checklist item now met:** "Admin API requires API key; without it, 401" ✓. Tests: `tests/unit/test_admin_api.py` (18: auth/404-gating/all endpoints), `test_admin_service.py` (2), `test_config.py` (+2), `tests/integration/test_admin_repositories.py` (+2 `list_recent`).

**Validation Results (all gates green; verified against live postgres:15 + redis:7):**
- `ruff check .` / `ruff format --check .` — clean.
- `mypy --strict .` — no issues in **178** source files.
- `lint-imports` — **7 contracts kept, 0 broken** (the broadcast worker imports only services/domain/core + sqlalchemy; repos arrive as session-bound factories from `workers/main.py`).
- `pytest` — **328 passed** (276 unit + 52 integration). New unit suites: `test_broadcast_service`, `test_broadcast_worker`, `test_admin_handler`, `test_settings_validation`; updated `test_bot_composition` (5 routers), `_fakes` (broadcast repo, audience/stats methods, settings `list_all`). New integration suite `test_admin_repositories` (user aggregate counts, broadcast-audience filter/cursor, broadcast lifecycle UPDATEs against the live DB).
- `bandit -r . -c pyproject.toml` — 0 findings.
- `pip-audit` — no new dependencies.

**Validation Checklist status:** 7 / 7 met — `/stats` totals ✓, `/ban`+`/unban` audit fields ✓, `/setting_set` type validation + bad-input rejection ✓, `/broadcast` queues + worker processes + counters reflect actuality ✓, `--lang`/`--role` audience targeting ✓, non-owner blocked from owner-only commands ✓, **"Admin API requires API key; without it, 401" ✓ (8.3, 2026-06-25)**.

**Known Issues / deviations (surfaced for Owner):**
- **8.3 implemented 2026-06-25** (above), `[~]` Under Review. The `ADMIN_API_KEY` §13.2/§20.3 conflict was resolved by adding the env var to §13.2 (D-051, Owner-approved). FastAPI/uvicorn were already approved for Sprint 10 (D-049). With a single shared key there is no per-request HTTP identity, so the §20.2 "(owner only)" markers collapse to "valid-key-only" in V1 (documented in §20.3).
- **BroadcastWorker polls the `broadcasts` table instead of the shared queue (deviation from §16.8 wording).** §16.8 says "enqueue a job with `worker_kind='broadcast'`", but V1's `RedisQueue` does not dispatch by `worker_kind` (the download worker `BZPOPMIN`-pops any member and treats it as a job UUID), and §11.4 defines no broadcast queue key. Polling the durable `pending` rows is the only correct V1 mechanism and matches the `BroadcastWorker` component card (no `QueueService` dependency). Ratify, or add a kind-aware queue later.
- **Pre-send confirmation prompt deferred.** The §23 risk table suggests a "confirmation prompt before sending"; `/broadcast` currently queues immediately and echoes the audience count. A Confirm/Cancel inline step would need a new `bcast:draft` Redis key (a §11.4 addition). Not a hard validation-checklist item.
- **Sprint 7 carry-over — `history_page_size` — RESOLVED 2026-06-24.** Sprint 7 hardcoded the history page size to 5; §13.4 defines a seeded `history_page_size` settings key (default 10) that `HistoryService` should read instead. Fixed: `HistoryService` now reads the page size via `SettingsService` (read-through cached, like `RateLimitService` reads its limits), falling back to 10 if the key is unseeded (`SettingNotFoundError`); the over-read-by-one next-page detection is unchanged. `make_history_service` (bot/main.py) injects the `SettingsService`. No §13.4 key or schema change. Operators can now tune it via `/setting_set` per the HistoryHandlers component card.

**Sprint Closeout — 2026-06-24**

Sprint 8 (Admin and Ops) ships the in-bot administration surface (8.1 + 8.2): Owner/Moderator can run `/stats`, `/userinfo`, `/ban`, `/unban`, `/settings`, `/setting_set`, and `/broadcast` from within Telegram, with role-gated authorization and a durable, crash-resilient broadcast fan-out worker. All automated gates pass (328 tests; ruff, mypy --strict 178 files, import-linter 7 contracts, bandit 0). No schema, dependency, or migration changes; `broadcast_chunk_size` uses the existing seeded settings key. Task 8.3 (the `/v1/admin/*` HTTP API) is deferred by Owner decision pending FastAPI-dependency approval. Stops here for Owner human-verification (run each admin command; send a broadcast) before Sprint 9.

---

### Sprint 9 — Smart Advertisements

| Field | Value |
|---|---|
| **Status** | `[~]` Under Review (code complete; awaiting Owner human-verification before Sprint 10) |
| **Completion** | 100% (4 / 4) |
| **Goal** | Admin manages ads; ads are delivered per the algorithm. |
| **Stop Point** | Owner creates an ad, runs downloads, sees the ad, clicks the button, confirms count rises. |

**Completed Tasks**

- [x] **9.1** `services/ad_service.py` — selection algorithm per Section 16.7 (post-increment modulo, D-010); impression increment; click tracking; admin CRUD + validation. Premium **and** `UNLIMITED_ROLES` (Owner) are exempt from untargeted ads (#21). → `services/ad_service.py`, `domain/protocols/advertising.py` (`AdSenderProtocol`/`AdClickSignerProtocol`/`AdShowProtocol`), `infrastructure/database/repositories/advertisement.py` (+`AdRepositoryProtocol`).
- [x] **9.2** Owner-only ad commands `/ad_create`, `/ad_list`, `/ad_edit`, `/ad_toggle`, `/ad_delete`, `/ad_stats`, `/ad_global` — silently ignored for non-owners (item #18). → `bot/handlers/ads.py`, wired via `ad_service_factory` in `bot/main.py`.
- [x] **9.3** `DownloadService._deliver` runs `AdService.maybe_show` for each **newly-delivered** waiter with their post-increment total; best-effort (an ad failure never fails the job; a retry never re-shows). → `services/download_service.py`, worker wiring in `workers/main.py`.
- [x] **9.4** Ad-click callback (`a|<ad_id>`, HMAC-signed) records the click and delivers the destination link (Telegram URL buttons fire no callback, so the button is a callback button). → `bot/callbacks/factory.py` (`pack_ad_click` + `a` action), `bot/handlers/ads.py` (`handle_ad_click`), `infrastructure/telegram/ad_sender.py`.

**Validation Results (2026-06-24):**
- **405 tests pass** (340 unit + 65 integration, live pg:15 + redis:7). New: `test_ad_service.py` (selection truth table §16.7 + CRUD + click), `test_ad_handler.py` (7 commands + click callback), `test_ad_repository.py` (live impression/click increments + role-ranked select), ad-hook tests in `test_download_service.py`, ad-click round-trip in `test_callback_factory.py`.
- ruff + ruff-format clean; mypy --strict 185 files; import-linter 7 contracts; bandit 0 issues (all severities). No schema/dependency/migration changes (the `advertisements` table + indexes shipped in Sprint 2).
- Validation checklist: ad frequency (post-increment) ✓, premium/Owner skip untargeted ✓, `target_role='premium'` premium-only ✓, `ads_enabled=false` suppresses all ✓, impressions/clicks persisted ✓, highest-priority wins (with frequency fall-through) ✓, photo/video/animation send paths ✓.

**Known Issues:**
- Ad-click UX: arbitrary external URLs cannot open directly from `answerCallbackQuery` (Telegram restricts `url` to game/`t.me` links), so the click button is a **callback** button — the handler records the click, then sends the link as a tap-able message. This is the only way to track clicks on arbitrary URLs.
- `workers/main.py` imports `bot.callbacks.factory.CallbackSigner` (the shared HMAC helper) to sign ad buttons the bot verifies — permitted by import-linter for a composition root; flagged for Owner awareness.

---

### Sprint 9.5 — Ads v2 (Advertisements expansion)

| Field | Value |
|---|---|
| **Status** | `[~]` Under Review (9.5.1–9.5.10 built + tested; awaiting Owner human-verification) |
| **Completion** | 100% (10 / 10) — 9.5.9 (ad_events) + 9.5.10 (scheduling) added 2026-06-25 (deferred-backlog) |
| **Goal** | Flexible, audience-targeted ads: broadcast ads, placement-based persistent ads, rich Telegram content, media reuse (file_id + copyMessage), audience segmentation, management commands. |
| **Stop Point** | Owner creates a targeted/rich ad, previews it, broadcasts it, confirms placement + audience behavior + per-button counts. |

**Definition (full spec):** MASTER_PLAN §23 "Sprint 9.5 — Ads v2". Decisions D-042–D-045. Config §13.6 (seeded by `202606240001`). Schema roadmap §19.3. Extension points EP-19/EP-20.

**Completed Tasks:**

- [x] **9.5.1** Migration `202606240001_ads_v2_schema` (advertisements ALTERs; `ad_buttons`, `ad_audience_rules`, `audience_segments`, `audience_segment_members`; `broadcasts.advertisement_id`; placement index; §13.6 seed) + models/repos/protocols + new enums (`AdPlacement`, `AdDeliveryMode`, `Audience*`; widened `AdType`). No data backfill — AdService dual-reads legacy ads.
- [x] **9.5.2** Multi-button rendering + per-button signed callbacks (`a|<ad_id>|<button_id>`) + per-button click counters + `/ad_preview` + `/ad_button_add`/`/ad_button_clear`.
- [x] **9.5.3** Widened `fields`-mode content: document / audio send paths (album → copy mode).
- [x] **9.5.4** `copy`-mode delivery (`bot.copy_message`, storage channel setting `ads_storage_chat_id`); `/ad_create delivery=copy` captures a replied-to message.
- [x] **9.5.5** `AudienceService` (include/exclude × role/plan/language/user_id/segment; OR-within / AND-across; legacy `target_role` fallback) + `/ad_audience` + `/ad_segment_create|_add|_remove|_list`.
- [x] **9.5.6** `placement` column + per-placement settings toggles + placement-aware `AdService.maybe_show`. Live surfaces: `post_download` (download completion), `home` (`/start`), `history` (`/history`), `broadcast` (`/ad_broadcast`). The `video_delivery`/`audio_delivery`/`quality_select` placement values exist and are selectable but their in-flow triggers are a follow-up (the `post_download` hook covers the download case).
- [x] **9.5.7** `/ad_broadcast` — `BroadcastService.create_from_ad` + `BroadcastWorker` copyMessage branch; delivery counts via `total_sent`/`total_failed`.
- [x] **9.5.8** Command surface (`/ad_enable`, `/ad_disable`, `/ad_preview`, `/ad_broadcast`, `/ad_audience`, `/ad_segment_*`, `/ad_button_*`); COMMANDS.md updated.

**Completed (deferred-backlog 2026-06-25):**

- [x] **9.5.9** `ad_events` analytics table — **IMPLEMENTED 2026-06-25** (`[~]` Under Review). Promoted the skeleton to `migrations/versions/202606250001_ad_events.py` (`down_revision=202606240001`); partitioned monthly by `created_at` like `error_logs`, no FKs, rolling 13-month window seeded, indexes `ix_ad_events_ad` + `ix_ad_events_type_created`. `AdEvent` model + `AdEventRepository` (`record` / `count_for_ad`). New `AdEventType` enum. **Recording wired OFF the delivery hot path (D-052):** `AdEventRecorderProtocol` port (sync, non-blocking) + a fire-and-forget `AdEventRecorder` adapter (own session, background `asyncio` task, best-effort) injected into `AdService` — impression recorded in `maybe_show`, click in `record_click` (now carries `user_row_id`, threaded from the bot ad-click handler). The `advertisements`/`ad_buttons` counters stay authoritative. Partitions keep rolling via the new `RUNTIME_PARTITIONED_TABLES` (the baseline-migration `PARTITIONED_TABLES` stays frozen); `ad_events` has no retention key, so it is not auto-dropped. Migration round-trip (downgrade↔upgrade) verified on the live DB. Tests: `test_ad_event_recorder.py` (4), `test_ad_event_recording.py` (5), `test_ad_events.py` integration (2), `test_schema.py` (ad_events table/partition/indexes).

- [x] **9.5.10** scheduling scaffold — **IMPLEMENTED 2026-06-25** (`[~]` Under Review). Migration `202606250002_scheduling`: nullable `scheduled_at` on `broadcasts` + `advertisements` + partial index `ix_broadcasts_scheduled`. **Broadcasts** = a **due-poller**: `BroadcastRepository.get_next_pending(now)` returns the oldest pending row whose `scheduled_at` is NULL or `<= now`, so the existing `BroadcastWorker` poll loop is the poller (no new worker). **Ads** = a "starts showing at" gate in `AdService.maybe_show` (future-scheduled ads are skipped until due). `BroadcastService.create`/`create_from_ad` accept `scheduled_at`; `AdService.create`/`edit` accept a `scheduled_at` field (`none` clears). Commands: `--at <ISO>` on `/broadcast` + `/ad_broadcast`, `scheduled_at=<ISO>` on `/ad_create` + `/ad_edit`. Shared parser `core/timeparse.py` (`parse_iso_datetime`). NULL = prior immediate/always-eligible behavior. Migration round-trip verified. D-053. Tests: `test_timeparse.py` (5), `test_scheduling.py` (9), `test_broadcast_worker.py` (+2 due-poller), `test_admin_handler.py` (+2 `--at`), `test_ad_handler.py` (+1 `--at`), `test_admin_repositories.py` (+1 due filter, integration).

**Validation Results (2026-06-25):** 441 tests pass (live pg:15 + redis:7). New suites: `test_audience_service.py` (targeting truth table), `test_ad_service_v2.py` (multi-button/copy-mode/placement/audience/preview), `test_ad_repository.py` (+buttons/rules/segments/broadcast-link), ad-broadcast worker test, new ad-handler command tests. ruff/format clean; mypy --strict 196 files; import-linter 7 contracts; bandit 0. Migration round-trips (downgrade↔upgrade) verified.
**Known Issues:** Album ads require `delivery=copy` (a media group can't carry an inline keyboard directly). Copy-mode needs a stored source message (delete it → dead ad). `workers/main.py` imports `bot.callbacks.factory.CallbackSigner` (composition-root wiring; import-linter-permitted).

---

### Sprint 10 — Observability and Backup

| Field | Value |
|---|---|
| **Status** | `[~]` Under Review (10.1–10.8 code/ops-complete; awaiting Owner human-verification of the restore-drill report + runbook) |
| **Completion** | 100% (8 / 8) |
| **Goal** | Production-grade across logs, metrics, alerts, and DR. (Security validation and load testing are Sprint 11.) |
| **Stop Point** | Owner reads restore-drill report; approves runbook. |

**Completed Tasks**

- [x] **10.1** Sentry process tagging: `core/sentry.py` `set_component()` (bot/worker/api) + `request_scope(correlation_id, job_id)` context manager; bot `LoggingMiddleware` tags each update, `DownloadWorker` tags each job. (Deliberate-exception capture per process is the Owner's manual check.)
- [x] **10.2** `/v1/metrics` (Prometheus) — `core/metrics.py` registry with the full Section 15.3 set (8 counters, 4 histograms, 4 live gauges); instrumented at JobService/DownloadService/DownloadWorker/CacheService/AdService/BroadcastWorker; renders ≥30 series (92 locally). Multiprocess aggregation via `PROMETHEUS_MULTIPROC_DIR` (D-050).
- [x] **10.3** Telegram alerter — `core/alerting.py` (`AlertThrottle` 1/fingerprint/5 min + `TelegramAlertProcessor`) + `infrastructure/telegram/alerter.py`; wired into bot + worker composition roots (CRITICAL log lines → alerts chat). Sentry-webhook path documented as deferred.
- [x] **10.4** `/v1/health` + `/v1/ready` — `api/` FastAPI process (`api/app.py`, `api/readiness.py`, `api/main.py`); readiness checks DB+Redis ping ≤500 ms, queue depth, worker heartbeat. Worker heartbeats via `infrastructure/redis/heartbeat.py` (`WorkerHeartbeat`). 503 when a dependency is down.
- [x] **10.5** `CleanupWorker` full duties — partition rollover + retention drops (`infrastructure/database/maintenance.py` + `partitioning.py` helpers, D-015 partitioned drop) + orphan sweeps (`active_downloads`/`job_waiters` `delete_orphaned`), via `DbMaintenanceProtocol` (keeps the worker infrastructure-free). Temp sweep unchanged.
- [x] **10.6** PgBouncer verified (D-020). **Fixed a real config bug:** the edoburu image defaulted to `LISTEN_PORT 5432`, leaving the published `6432` dead — set `LISTEN_PORT=6432` + `ADMIN_USERS`/`STATS_USERS`. `SHOW POOLS` confirms transaction pooling; data path works on 6432.
- [x] **10.7** Backup-restore drill — PASS. `pg_dump -Fc` → throwaway DB → `pg_restore` → integrity match (head `202606240001`, all row counts, 260 partitions, sample query). Reports: `deploy/restore-drill-report.md` + `PERFORMANCE_REPORT.md` DR section.
- [x] **10.8** Operational runbook at `deploy/README.md` — topology, config, deploy, rollback, backup verify, and the 5 most-likely failure modes with responses.

**Validation Results:** ruff + format clean; mypy --strict 212 files; import-linter 7 contracts; bandit 0; **pytest 473 passed** (live pg:15 + redis:7), +28 new tests over Sprint 9.5's 445. New deps (Owner-approved 2026-06-25, D-049/D-050): `fastapi==0.115.6`, `uvicorn==0.34.0`, `prometheus-client==0.21.1`. No schema change; no new migration (Sprint 10 touches no tables). No new env vars (all observability keys already in §13.2/.env.example).
**Known Issues:** (1) Cross-process metric **counters** read ~0 at `/v1/metrics` unless `PROMETHEUS_MULTIPROC_DIR` is set (the live gauges are always accurate); deploy wiring of that shared volume lands with the app containers in Sprint 12. (2) `telegram_send_seconds` histogram is defined/exposed but not yet observed (NotificationService not instrumented). (3) Sentry "deliberate test exception per process" + "forced CRITICAL → Telegram alert" are Owner **manual** checks (Sentry is DSN-gated, off in dev). (4) The `api` process is run directly (`python -m api.main`); adding it to `docker-compose` with the bot/worker app containers is Sprint 12 scope.
**Owner action:** read `deploy/restore-drill-report.md` + approve `deploy/README.md`; optionally force a CRITICAL log + a test Sentry exception in a DSN-configured env to confirm alerts/captures. Then sign off Sprint 10.

---

### Sprint 11 — Testing Framework, Security Validation, Load and Stress

| Field | Value |
|---|---|
| **Status** | ✅ **Phase A — Completed & ARCHIVED (Gate G-5 approved 2026-06-27)** · ⏳ **Phase B — Waiting for Infrastructure** |
| **Phase A (implementation)** | **COMPLETE — all 9 code-only tasks done, gated, committed, pushed, and signed off (2026-06-27).** 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9. There is **no remaining code work** in Sprint 11; the framework, security suite, simulation, and E2E scaffolding are finished. |
| **Phase B (infra-dependent validation)** | **WAITING FOR INFRASTRUCTURE.** 11.10–11.14 are not code — they are *live executions* that require the Owner to provision the @BotFather sandbox bot + isolated test PG/Redis/storage. See the **Phase B Checklist** below (the handoff for the future Phase-B session). |
| **Completion** | Phase A: **9/9 (100%)**. Phase B: **0/5** (blocked on infra). Overall Sprint 11: 9/14 tasks; the remaining 5 are infrastructure-gated, not implementation. |
| **Goal** | A reusable, reproducible test framework — covering security, load, stress, and Telegram E2E — is implemented (Phase A ✅) and run live (Phase B ⏳). |
| **Stop Point** | **Gate G-5 (Security config) ✅ approved by Owner 2026-06-27 — Phase A signed off & archived.** Phase B closes after the live runs + capacity sign-off against `TEST_RESULTS.md` / `SECURITY_REPORT.md` / `PERFORMANCE_REPORT.md` (resumes when sandbox infra is ready). |
| **Phasing** | Owner-approved 2026-06-27: **code-first, defer live runs.** Phase A (framework code, no live bot) is built + gated + pushed; Phase B (live L1–L4, ST-1…6, S-1…S-5, capacity, manual M-17…22) runs once the sandbox bot + isolated test infra exist. |

**Completed Tasks — Phase A · ✅ Completed / Signed Off 2026-06-27** (all gated green, committed `4ac5f0b`…`14816d0`, pushed to `origin/claude/happy-bose-71ed46`)

- [x] **11.1** ✅ Completed / Signed Off — `DEPLOY_ENV` plumbing + production-fingerprint boot assertion — **2026-06-27.** Added LOCKED §13.2 keys `DEPLOY_ENV` + `PROD_BOT_TOKEN_FINGERPRINT` (Owner-approved, D-060). New extensible safety-rule registry `core/environment.py` (`ENVIRONMENT_SAFETY_RULES` + `evaluate_environment_safety` + `EnvironmentMisconfiguredError`) run by a self-enforcing `Settings._enforce_environment_safety` model-validator; `core/security.py::token_fingerprint` (SHA-256). First rule refuses to boot a `DEPLOY_ENV=test` process against the production bot. First occupant of `tests/security/`. **Validation:** 691 pass (+20) / 0 fail / 2 deselected; ruff+format clean; mypy --strict 160; import-linter 7; bandit 0. No schema change. Touches security config → **Gate G-5 ✅ approved 2026-06-27**. *Sandbox-bot creation + test PG/Redis/storage provisioning is the Owner's Phase-B action.*

- [x] **11.5** ✅ Completed / Signed Off — Security test suite — all five §25.9 categories — **2026-06-27.** `tests/security/{input_validation,authorization,abuse_protection,data_protection,dependency_scan}` (+ the 11.1 isolation test) = 45 security tests. `pip-audit`+`bandit` already wired in `.github/workflows/ci.yml` (verified, not duplicated). **Validation:** 732 pass (+41) / 0 fail / 2 deselected; ruff+format clean; mypy --strict 160; import-linter 7; bandit 0. No source change. Touches security → **Gate G-5 ✅ approved 2026-06-27**.

- [x] **11.2** ✅ Completed / Signed Off — E2E harness — **2026-06-27.** `tests/e2e/harness.py`: `E2EHarness` (sandbox-bot client wrapper; `connect` is Phase B), `AccountPool` + `SandboxAccount` (fixed test-account pool, round-robin), `DeterministicDelays` (seeded), `sandbox_ready`/`skip_if_sandbox_unavailable` gating on `DEPLOY_ENV=test` + `E2E_LIVE=1`. `tests/e2e/conftest.py` exposes the `harness` fixture (skips when the sandbox is unavailable). Harness self-tests `tests/e2e/test_harness.py` (5, run now). 

- [x] **11.3** ✅ Completed / Signed Off — E2E flow suites — **2026-06-27.** `tests/e2e/{bot_core,download_flow,cache_flow,queue_flow,error_flow}/` cover every §25.7 scenario (23 tests), all skip-guarded via `harness` until Phase B.

- [x] **11.4** ✅ Completed / Signed Off — Named E2E scenarios S-1…S-5 — **2026-06-27.** `tests/e2e/scenarios/test_scenarios.py` (5, skip-guarded). S-3 documents the mocked-secondary-provider failover. **Validation (11.2–11.4):** 766 pass (+5 harness) / 28 skipped (flow+scenario, Phase B) / 0 fail / 2 deselected; ruff+format clean; bandit 0. Live execution of S-1…S-5 is Phase B (11.10+).

- [x] **11.6** ✅ Completed / Signed Off — `tests/simulation/` framework skeleton — **2026-06-27.** `SimulationRunner` (+ `LOAD_LEVELS` L1–L6, `reject_production_credentials` in `__init__`, §25.15.9 CLI `python -m tests.simulation.runner`), `BotClient` ABC + deterministic network-free `StubBotClient` (models rate/daily/rapid-fire defenses; `SandboxBotClient` is a Phase-B placeholder), `UserProfile` base + `PROFILE_REGISTRY`, `MetricsCollector`/`RunSummary` (p50/p95/p99, error rate, throughput, blocked-download count), append-only `ReportWriter`, `SimulatedAction`/`ActionResult`. Self-tests in `tests/unit/test_simulation_framework.py` (8). **Validation:** 740 pass (+8) / 0 fail / 2 deselected; ruff+format clean; mypy --strict 160 (tests excluded); bandit 0. *Live sandbox transport + real load runs are Phase B.*

- [x] **11.9** ✅ Completed / Signed Off — Stress-scenario catalog ST-1…ST-6 — **2026-06-27.** `tests/simulation/scenarios/__init__.py`: `ScenarioCatalog` + `STRESS_SCENARIOS` with each scenario's LOCKED expected behavior (§25.15.6). Load-shaped ST-1 (100→1000 spike) + ST-2 (5000-job flood) carry deterministic traffic-plan builders; fault-injection ST-3/4/5/6 (cache storm, provider outage, DB slowdown, Redis restart) are specs executed against live infra in Phase B (11.11). Tests in `tests/unit/test_stress_scenarios.py` (7). **Validation:** 761 pass (+7); ruff+format clean; bandit 0.

- [x] **11.8** ✅ Completed / Signed Off — AI-controlled traffic generators — **2026-06-27.** `tests/simulation/traffic/`: `RandomTraffic`, `ScheduledSpike`, `PeakHour`, `Viral`, `PlatformPattern` self-register in `TRAFFIC_REGISTRY`. Each produces a deterministic `TrafficPlan` (per-user `Spawn(profile, start_offset_s)`) — profile mix for the stub runner now, arrival-timing for Phase-B live runs. Tests in `tests/unit/test_traffic_generators.py` (9: registry, determinism, window bounds, spike-clustering, viral monotonicity, peak concentration, platform validation). **Validation:** 754 pass (+9); ruff+format clean; bandit 0.

- [x] **11.7** ✅ Completed / Signed Off — Five V1 user profiles — **2026-06-27.** `Casual`/`Active`/`Heavy`/`Abuse` (registered in `PROFILE_REGISTRY` via `@register_profile`); `Premium` present but disabled (`enabled=False`, not registered) until V2. Each emits a deterministic action stream. Verified: `python -m tests.simulation.runner --level=L1 --profile=Abuse --seed=42` → 0 successful downloads (M-22 invariant); `--profile=Casual` → downloads succeed. Tests in `tests/unit/test_user_profiles.py` (5). **Validation:** 745 pass (+5); ruff+format clean; bandit 0.

### ⏳ Phase B Checklist — Waiting for Infrastructure (handoff for the future Phase-B session)

No code work remains in Sprint 11. Phase B is purely infrastructure provisioning +
live execution. Work top-to-bottom; each block is a prerequisite for the next.

**Provision isolated test infrastructure (Owner):**
- [ ] Create the @BotFather **sandbox bot** (separate from production); capture its token
- [ ] Configure **isolated PostgreSQL** (test instance / `test_*` schema; run `alembic upgrade head`)
- [ ] Configure **isolated Redis** (separate logical DBs, e.g. 4/5; `test:` queue prefix)
- [ ] Configure **isolated storage** (e.g. `/tmp/test_downloads`) + a dedicated test owner account
- [ ] Set **`DEPLOY_ENV=test`** (and `PROD_BOT_TOKEN_FINGERPRINT` = prod token SHA-256, so the boot assertion guards the sandbox)
- [ ] Enable **`E2E_LIVE=1`** (arms the live E2E transport)

**Implement the two live transport seams (small Phase-B code):**
- [ ] `tests/simulation/bot_client/client.py::SandboxBotClient` — real sandbox transport
- [ ] `tests/e2e/harness.py::E2EHarness.connect` — open sandbox session + drive test accounts

**Execute live validation:**
- [ ] **Execute L1–L4** end-to-end → append per-level entries to `PERFORMANCE_REPORT.md` (11.10)
- [ ] **Execute ST-1…ST-6** (incl. fault-injection ST-3/4/5/6) → append outcomes (11.11)
- [ ] **Execute S-1…S-5** named scenarios against the sandbox (11.4 live)
- [ ] **Run full regression + every security category live** (incl. E2E) → `TEST_RESULTS.md` + `SECURITY_REPORT.md` (11.12)
- [ ] **Generate the final capacity report** (§25.15.7: max users, downloads/hr, queue throughput, +50% hardware, scaling rec.) (11.13)
- [ ] **Update `PERFORMANCE_REPORT.md`** Status-Summary capacity rows with real numbers; confirm V1 SLOs hold at L4
- [ ] **Record M-17/M-18/M-19/M-20** in the Manual Test Catalog (M-21/M-22 already ✅ in Phase A) (11.14)
- [ ] **Mark Sprint 11 complete** — meet the Exit Criteria; Owner signs off the capacity report

**Already pre-validated in Phase A (no fabricated live numbers):** L1–L4 framework dry-run via the deterministic stub (runs to completion; reproducible `PERFORMANCE_REPORT.md` entry, clearly labelled *not* capacity); ST-1/ST-2 traffic-plan shapes; full **automated** regression + all 5 security categories green (766 pass / 28 e2e-skipped); capacity-report methodology stub; **M-21** (security categories pass) + **M-22** (abuse blocked, 0 successful downloads at L2).

**Validation Results:** Phase A — 766 pass / 28 skipped (E2E, Phase-B-gated) / 2 deselected; ruff + format clean; mypy --strict 160; import-linter 7; bandit 0. Phase B — pending infrastructure.
**Known Issues:** none.
**Next Recommended Action:** Phase A is finalized, **Gate G-5 ✅ approved (2026-06-27)**, and archived. Phase B stays parked until the sandbox infra is ready. Development continues with **Sprint 12 — Launch Readiness** in a new session (see that section + the kickoff prompt the Owner was given).

---

### Sprint 11.5 — Internationalization (i18n)

| Field | Value |
|---|---|
| **Status** | `[~]` Implemented (2026-07-01) — code/tests complete; live-bot human-verification parked for Sprint 11 Phase B (needs the sandbox bot, same as 11.10–11.14) |
| **Completion** | 100% (12 / 12) — decimal sub-sprint like 9.5; not folded into the fixed 105-task Sprint Overview total |
| **Goal** | Every piece of bot UI copy renders in the user's own language. English + Arabic ship now; any future language is a content-only addition (one catalog file), with zero business-logic change. |
| **Stop Point** | Agent stops after the 12 tasks per the standard per-task DoD. Live-bot verification (Arabic RTL round-trip, admin-panel-only-chrome-changes check, multi-language fan-out) is explicitly deferred to Sprint 11 Phase B — not a blocker for marking 11.5 code-complete. |

**Why now, not V2:** The Owner supplied a complete localization spec mid-session while Sprint 12 was in progress. MASTER_PLAN §2.4 had reserved "Multi-language interface" for V2; asked directly, the Owner chose to pull it into V1 now. The design itself went through three rounds of Owner simplification during review (full history: MASTER_PLAN D-061–D-064) — landing on no first-contact gate, no `/language` command, filesystem-discovered locales instead of a `settings`-table list.

**Definition (full spec):** MASTER_PLAN §23 "Sprint 11.5 — Internationalization (i18n)". Decisions D-061–D-064. Env var §13.2 (`DEFAULT_LOCALE`). No migration, no new settings key — see D-061/D-062.

**Completed Tasks:**

- [x] **11.5.1** `core/i18n.py` — catalog discovery/validation (`_meta` contract, default-locale-as-reference-catalog invariant, never raises) + `core/locales/en.json` + `ar.json` (~250+ keys each) + `Settings.default_locale` (`DEFAULT_LOCALE` env var).
- [x] **11.5.2** `UserFacingError.translation_key` on the domain exception hierarchy (traced every raise site first; no generic `params` dict added, since nothing would have consumed it).
- [x] **11.5.3** `UserService.set_language(telegram_id, language)`, mirroring the existing `ban`/`unban`/`set_premium` mutation pattern.
- [x] **11.5.4** `AuthMiddleware` seeds a new user's `users.language` from `Settings.default_locale` (never Telegram's auto-detected `language_code`); new `LocaleMiddleware` (`bot/middlewares/i18n.py`) resolves `data["locale"]` fresh every update (after `auth`, before `throttle`).
- [x] **11.5.5** Composition-root wiring: `dp["translate"] = core.i18n.translate` in `bot/main.py`; both `bot/main.py` and `workers/main.py` call `i18n.configure(settings.default_locale)` at their own startup.
- [x] **11.5.6** `bot/keyboards/language_select.py` (picker) + signed callback action `l` (`CallbackSigner.pack_language`) + both entry points: "🌐 Change Language" button on `/start` (regular users), "🌐 Language" admin-panel section (Owner/Moderator) — one shared apply path in `bot/handlers/start.py`.
- [x] **11.5.7** `NotificationService` (`send_initial`/`notify_stage`/`notify_completed`/`notify_failed`) takes a required `locale`; `DownloadService._notify_waiters` + `JobService._try_deliver_cached` resolve each fan-out recipient's own locale fresh (a job's waiters aren't guaranteed to share a language).
- [x] **11.5.8** Migrated the regular-user surface: `bot/handlers/{start,help,download,history}.py`, `bot/keyboards/{format_select,quality_select,history}.py`, `bot/middlewares/{throttle,auth}.py`.
- [x] **11.5.9** Migrated `bot/panel/registry.py` — all six registries (`Section`/`MenuItem`/`SettingField`/`InfoItem`/`AudienceOption`/`PlacementOption`) swap `label` → `label_key`; new `Section("l", "panel.section.language")` added.
- [x] **11.5.10** Migrated `bot/keyboards/admin_panel.py`'s own literals (every builder function, ~40+ labels incl. the compose-wizard screens).
- [x] **11.5.11** Migrated `bot/handlers/{admin,ads,admin_panel,admin_wizard}.py` — the full admin/ads command surface + the FSM compose wizard.
- [x] **11.5.12** New `tests/unit/test_i18n.py` (22 tests: catalog validation, fallback chain, real-catalog invariants, incl. a regression test for the `translate(key, locale, **kwargs)` / `{key}`-placeholder collision found and fixed this sprint); every existing test file touched by a handler-signature change updated; full suite + ruff + mypy --strict re-verified clean.

**Validation Results (2026-07-01):** 853 tests collected, **0 failures / 0 errors**, 114 skipped. Skips are **all integration (`tests/integration/`) + e2e (`tests/e2e/`) tests that require live Postgres/Redis/a sandbox bot** — this session's environment has none running (no Docker daemon available), so they skip cleanly rather than error; this is an environment constraint, not a code regression (the same tests passed live in prior sessions per this file's earlier validation entries, e.g. "live pg:15 + redis:7"). ruff check + format clean. mypy --strict: 37 errors in 12 files — **all pre-existing and unrelated to this sprint**, confirmed by a clean-cache baseline comparison against the original commit (42 errors / 13 files before, i.e. this sprint's changes net **reduced** mypy errors by fixing an incidental pre-existing suppression gap in `test_admin_wizard.py` while touching those exact lines anyway) and by `git diff` showing zero changes to 8 of the 12 still-erroring files. import-linter: 7/7 contracts kept. bandit: 0 issues (all severities). No schema/migration, no new settings key — Gate G-2 not triggered; no auth/queue/provider/security-config change — no other §25.13 gate triggered either.
**Known Issues:** None new. Pre-existing, unrelated mypy gaps remain in test doubles (`FakeMessageSender` vs `MessageSenderProtocol` missing `parse_mode`; a few fake-vs-real-protocol mismatches in `test_authorization.py`/`test_ad_placements.py`/`test_broadcast_worker.py`/`test_wizard_engine.py`/`test_job_service.py`/`test_history_service.py`/`test_broadcast_service.py`/`test_bot_composition.py`) — none touched by this sprint, all confirmed via `git diff` to predate it.
**Next Recommended Action:** Resume **Sprint 12 Phase A remainder** (A2–A6, unaffected by 11.5). Sprint 11.5's own remaining item — the live-bot walkthrough (Arabic RTL rendering, admin-panel-only-chrome-changes check, multi-language fan-out) — is parked for **Sprint 11 Phase B** alongside the rest of that phase's infra-gated work; no separate blocker.

---

### Sprint 12 — Launch Readiness

| Field | Value |
|---|---|
| **Status** | `[~]` Phase A COMPLETE (A1–A6, code/docs) — Phase B (12.1–12.7) Owner-infra-blocked |
| **Completion** | Phase A 100% (6 / 6); Phase B 0% (0 / 7, blocked) |
| **Goal** | Bot ready for public traffic. |
| **Stop Point** | Owner signs off on smoke tests + E2E reruns + release entries in all three report files. V1 complete. |

**Phase A — deploy prep (code/docs, no production infra needed) — COMPLETE**

- [x] **A1** `deploy/docker-compose.prod.yml` — app tier (bot/worker/api) over the postgres/redis/pgbouncer/uptime-kuma infra (`d06b583`, 2026-07-01).
- [x] **A2** `.env.production.example` — production app-config template mirroring the LOCKED §13.2 key set, placeholder-only secrets; `.gitignore` exception; gate tests in `test_config.py` (`9e77ed4`, 2026-07-06).
- [x] **A3** `deploy/smoke-test.sh` (scripted endpoint checks) + `deploy/SMOKE_TEST.md` (full launch checklist incl. the manual bot-flow half) (`3ebbbed`, 2026-07-06).
- [x] **A4** `deploy/RELEASE_CHECKLIST.md` — ordered release procedure (gates → build/tag → migrate → deploy → smoke → sign-off) + rollback (`45b5e22`, 2026-07-06).
- [x] **A5** `.github/workflows/release.yml` — tag-triggered gate re-run + prod-compose validation + image build; publish/deploy left Owner-infra-gated (`b27db7e`, 2026-07-06).
- [x] **A6** Runbook drift fix — `deploy/README.md` + compose head comment corrected to `202607050003`, §3 rewritten for prod compose, admin-API line corrected to opt-in/D-051 (`849965d`, 2026-07-06).

**Phase B — production deploy (BLOCKED on Owner infra: OQ-1 Sentry, OQ-3 host, OQ-5 alerts chat; transitively on Sprint 11 Phase B)**

- [ ] **12.1** Deploy bot, worker, api containers to production.
- [ ] **12.2** Configure Sentry production project + Uptime Kuma monitors.
- [ ] **12.3** Production smoke tests (`/start`, cached download, fresh download, `/stats`, ad, ban/unban). — checklist + script shipped (A3); execution needs the live stack.
- [ ] **12.4** Re-run E2E scenarios S-1 and S-2 against production.
- [ ] **12.5** Hand off runbook to Owner. — runbook current (A6); hand-off is the Owner walkthrough.
- [ ] **12.6** Schedule first restore drill (30 days post-launch) + first L4 production-shadow load run (90 days post-launch).
- [ ] **12.7** Mark V1 complete; append release entries to `TEST_RESULTS.md`, `SECURITY_REPORT.md`, `PERFORMANCE_REPORT.md`.

**Validation Results:** Phase A — `test_config.py` gates green (23 tests, incl. the new production-example build/parity/no-secrets checks); `smoke-test.sh` syntax-checked (`sh -n`) and failure-path verified (exit 1 against a dead port); `release.yml` valid YAML; single Alembic head confirmed `202607050003`. Phase B — pending (needs production infra).
**Known Issues:** none.

---

### Sprint 13 — Admin Panel Enhancement and Growth Features

| Field | Value |
|---|---|
| **Status** | `[~]` Implemented (2026-07-05) — code/tests complete; awaiting Owner sign-off + a push decision |
| **Completion** | 100% (9 / 9) — new numbered sprint, out of the original 0–12 order (Owner-requested mid-flight; tracked in its own Sprint Overview row like the 9.5/11.5 decimals, not yet folded into the fixed 105-task total) |
| **Goal** | Turn the Sprint 9.6 admin panel from a functional-but-plain chat UI into a "Dashboard Grade" experience, and add six growth/ops features (platform analytics, richer activity metrics, account-health detection, subscriber export/import, a referral program, and admin-editable message templates) — all discoverable from a live main-menu dashboard. |
| **Source spec** | `SPRINT_13_PLAN.md` (SSOT for scope, design system, screen mockups) + `SPRINT_13_PROMPT.md`, both at the worktree root, Owner-authored. |
| **Stop Point** | Owner reviews the design (screenshots or a live-bot walkthrough) and the 19-commit diff, then signs off. Push is explicitly gated — not done automatically per standing session rule. |

**Worktree note:** this sprint was executed in `happy-bose-71ed46` (branch `claude/happy-bose-71ed46`) — confirmed as the live worktree per this repo's convention (other worktrees under `.claude/worktrees/` are stale clones at older commits). The session that did this work was launched in a different, freshly-created worktree; the Owner was asked and explicitly redirected the work here before any code was written.

**Completed Tasks:**

- [x] **13.1** `bot/panel/ui.py` — the "Dashboard Grade" primitives (`header`/`divider`/`metric`/`progress_bar`/`sparkline`/`badge`/`card`/`table`/`footer`/`status_dot`/`role_icon`/`number_fmt`/`time_ago`), pure presentation (no I/O), every dynamic value HTML-escaped, RTL-aware without a locale argument (content-sniffed). Plus an **animation-ready emoji layer**: every icon is a semantic code routed through `ui.emoji(code)`, backed by an empty `CUSTOM_EMOJI_IDS` map — filling that map (once the bot has a Fragment-purchased username, a Bot-API requirement for animated custom emoji) switches the whole panel to animated icons with zero screen changes. Ships with plain Unicode today by design. 50 tests.
- [x] **13.2** Full UI redesign: main-menu **live dashboard** (5 key metrics before any tap — `open_panel` signature changed to inject `user_service_factory`/`queue_service`), Statistics screen (surfaces the new 13.4/13.5 metrics), User-detail screen (rebuilt as a `ui.card` profile block + a divider'd activity metrics block), Downloads and System status screens (metric-line dashboards). **Residual redesign COMPLETE (2026-07-06):** user-list rows + tappable Users list, moderation banned list (via the shared `_user_row`, which also upgraded the 13.5 blocked/deleted health lists), errors + recent/active jobs lists, ads list/detail (`ui.card`)/picker/totals, grouped Settings screen (7 labelled groups via `ui.divider`, order preserved so text still matches the stepper buttons), and the Broadcast section screen are now all rendered through `bot/panel/ui.py`. Pure presentation, zero behavior change; catalog parity held at 464/464 en/ar keys (monolithic body keys retired, plain title keys + field-label/group-title keys added). 779 unit tests green, mypy --strict 174 files, import-linter 7/7.
- [x] **13.3** Per-platform download analytics: `DownloadRepository.count_by_platform`/`total_count` (optional `since`); `AdminService.get_platform_stats(period)` / `get_platform_report()` (today/week/month/all, per-platform share %); a new Statistics sub-screen rendering `ui.sparkline` bars per platform + a compact period-filter row; owner-only **CSV export** (`download_stats_<date>.csv`) sent as a Telegram document.
- [x] **13.4** Enhanced user-activity metrics: `UserRepository.count_active_in_hours`/`count_inactive_days`/`count_active_current_hour`/`count_active_previous_hour`; `UserStats` gains `active_24h`/`7d`/`30d`, `inactive_5d`/`7d`/`30d`, `active_current_hour`/`previous_hour` (all default 0, non-breaking); surfaced in the redesigned Statistics screen.
- [x] **13.5** Blocked-bot / deleted-account detection: migration `202607050001` adds `users.bot_blocked`/`is_deleted`/`status_checked_at` + an index; `UserRepository` count/list/mark/purge methods; `services/user_health.py::UserHealthChecker` (framework-free — probes via an injected `ChatProber` protocol, persists via a `UserHealthStore` protocol) does a batched, delayed full sweep with a progress callback. Bot-layer `bot/chat_prober.py::AiogramChatProber` maps `TelegramForbiddenError`→blocked / "not found"→deleted over `Bot.get_chat`; infra `infrastructure/database/user_health_store.py::UserHealthStoreAdapter` runs each step on its own committed session (mirrors `AdEventRecorder`'s D-052 pattern) so the sweep never holds the request transaction open. Moderation section gained **Check Status** (runs the sweep, reports active/blocked/deleted/error counts + duration), **Blocked/Deleted lists**, and **Purge** (destructive, confirm-gated).
- [x] **13.6** Subscriber export/import: `UserService.export_users(fmt)` → CSV or JSON bytes (paged over all rows); `import_users(rows)` → `ImportResult` (created/skipped/failed, **create-only, never overwrites**). Users section gained owner-only Export (format picker → document) and Import (new `import_subscribers` FSM state; the uploaded `.csv`/`.json` is parsed and bulk-imported, replying with counts).
- [x] **13.7** Full referral system: migration `202607050002` adds `users.referred_by_id`/`referral_code`/`referral_bonus_downloads` + a `referrals` table + seeds `referral_enabled`/`referral_reward_downloads` settings; `services/referral_service.py::ReferralService` (idempotent unique code generation, `process_referral` with self/duplicate/disabled/not-found guards, permanent stacking bonus to both sides, dashboard + leaderboard). `/start` parses `?start=ref_CODE`, applies the referral, and best-effort-notifies the referrer (swallows `TelegramAPIError` if they blocked the bot); new `/referral` command shows the user's own link/invites/bonus; new admin section **`r`** (Referrals) renders the dashboard + top-5 leaderboard via `ui.sparkline`.
- [x] **13.8** Admin-editable message templates: migration `202607050003` adds a `message_templates` table (PK `key`+`locale`); `services/template_service.py::TemplateService` over 9 editable keys, with a transparent hook added to `core/i18n.py` (`translate()` now consults an in-memory override map before the on-disk catalog; `catalog_template()` exposes the raw shipped default for previews) — so overriding a template changes live bot copy immediately, with zero change to any caller of `translate()`. Wired as a **process singleton** (loaded once at startup) via a new session-owning `infrastructure/database/message_template_store.py::MessageTemplateStore` adapter. New owner-only admin section **`tp`** (Templates): list (✏️ custom / 📄 default), edit (arms a `template_edit` FSM state), reset-to-default (confirm-gated).
- [x] **13.9** Registry/FSM/composition wiring for all of the above: new sections `r`/`tp` (+ `tp` is `owner_only`), submenu extensions on `t` (platform stats), `u` (export/import), `m` (5 health-detection items); new `READ_ACTIONS` entries `lsb`/`lsd` (blocked/deleted lists stay read-tier); new FSM states `import_subscribers`/`template_edit`; `bot/main.py` composition root gained `referral_service_factory`, the `template_service` singleton (+ its `.load()` at startup), and `health_checker_factory(bot)` (resolves the bot's own `@username` once via `get_me()` for the referral deep-link); every new i18n key added to **both** `core/locales/en.json` and `core/locales/ar.json` (parity-checked by `core.i18n.configure`'s reference-catalog invariant — a missed Arabic key fails startup, not silently).

**Validation Results (2026-07-05):** Full `tests/unit` suite green (exit 0, no failures) after every one of the 18 feature commits — re-run in full at the end too. `ruff check` + `ruff format --check` clean throughout. `mypy --strict` across `bot/ core/ domain/ infrastructure/ services/ workers/ api/`: **0 issues, 174 source files** (grew from the Sprint 11.5-era baseline as new modules were added). `lint-imports`: **7/7 contracts kept** at every commit, including the two layer-sensitive additions this sprint — `services/user_health.py` stays aiogram-free via an injected `ChatProber` protocol (the aiogram exception mapping lives in the new `bot/chat_prober.py`), and both new DB-store adapters (`user_health_store.py`, `message_template_store.py`) satisfy their service-layer protocols structurally without `infrastructure` importing `services`. Dev Postgres was one migration set behind at the start of this session (`202606270002`), causing a live `UndefinedColumnError` on `users.bot_blocked` when the bot was started against it — resolved by running `alembic upgrade head` (now `202607050003`); confirmed via direct query that the new columns, `referrals`/`message_templates` tables, and the two seeded referral settings all exist.
**Known Issues:** None new. Animated emoji is **wired, not enabled** — Telegram's Bot API restricts `<tg-emoji>` custom-emoji entities to bots with a Fragment-purchased username; `bot/panel/ui.py::CUSTOM_EMOJI_IDS` is the single switch, currently empty, so every icon renders as plain Unicode (by design, not a bug) until the Owner supplies a Fragment username + the custom emoji ids. The 13.2 residual list above (a handful of secondary read screens not yet passed through `ui.py`) is cosmetic and non-blocking. `graphify-out/` generated artifacts were accidentally swept into one commit by a background hook (`git add -A`); untracked + gitignored in a follow-up chore commit (`0c523d3`) — a reminder to stage explicit paths rather than `-A` in this repo going forward.
**Next Recommended Action:** Owner reviews (ideally by running the live bot — migrations are already applied) and signs off, or requests the residual 13.2 polish first. Push is **not** done automatically — ask before pushing `claude/happy-bose-71ed46`.

---

## Files Modified Log

Append a row when a PR merges. Newest first.

| Date | PR | Files Affected | Sprint / Task | Author |
|---|---|---|---|---|
| 2026-07-01 | — (uncommitted) | **Sprint 11.5 — Internationalization (i18n), implemented in full.** New: `core/i18n.py`; `core/locales/{en,ar}.json`; `bot/middlewares/i18n.py` (`LocaleMiddleware`); `bot/keyboards/language_select.py`; `tests/unit/test_i18n.py`. Updated: `core/config.py` (`default_locale`/`DEFAULT_LOCALE`) + `.env.example`; `domain/exceptions.py` (`UserFacingError.translation_key`); `services/user_service.py` (`set_language`); `services/{notification_service,download_service,job_service}.py` (required/per-recipient `locale`); `bot/middlewares/auth.py` (default-locale seeding); `bot/main.py` + `workers/main.py` (composition-root `i18n.configure`/`dp["translate"]`); `bot/callbacks/factory.py` (signed `l` action); `bot/handlers/{start,help,download,history,admin,ads,admin_panel,admin_wizard}.py`; `bot/keyboards/{format_select,quality_select,history,admin_panel}.py`; `bot/panel/registry.py` (`label` → `label_key` across all six registries + new Language section). Tests updated: `tests/conftest.py` (autouse i18n configure fixture) + `tests/unit/{test_bot_middlewares,test_bot_handlers,test_download_handler,test_history_handler,test_keyboards,test_notification_service,test_admin_handler,test_ad_handler,test_admin_panel_handler,test_admin_panel_keyboards,test_admin_wizard,test_exceptions}.py`. Docs: `MASTER_PLAN.md` (new §23 Sprint 11.5 section; D-061–D-064; §2.4/§3/§9/§10.2/§10.13/§13.2/§17/§18/§25.7.1/§27); `project_reference.md` (§23.2/§23.3 rewritten); `PROJECT_PROGRESS.md` (this entry + Sprint 11.5 detail + overview/state updates). No migration — reuses existing `users.language` (D-061). | Sprint 11.5 / 11.5.1–11.5.12 | Implementation agent |
| 2026-06-25 | — (uncommitted) | **Owner feedback #28–#31.** #28/#29 (quality + size accuracy): `infrastructure/downloader/providers/ytdlp_provider.py` (`_format_selector` downloads the exact offered `format_id`; capped fallback, no uncapped `/best`) + `tests/unit/test_ytdlp_provider.py`. #30 (ad under media): `domain/protocols/file_sender.py` + `infrastructure/telegram/file_sender.py` (`upload`/`send_cached` return message id); `services/download_service.py` (capture + pass `reply_to_message_id`); `domain/protocols/advertising.py` + `services/ad_service.py` + `infrastructure/telegram/ad_sender.py` (thread `reply_to_message_id`). #31 (direct-open URL buttons): `AdButtonSpec` (+`url`), `ad_sender._build_markup`, `AdService._build_buttons`. Tests: `tests/unit/{_fakes,test_file_sender,test_download_service,test_ad_service,test_ad_service_v2}.py`. Docs: `MASTER_PLAN.md` (D-046–D-048; EP-21–23; §23 F-1/F-2/F-3 roadmap for #32–#34), `COMMANDS.md`, `ADS_MANUAL_TEST.md`. | Post-9.5 feedback #28–#31 | Implementation agent |
| 2026-06-25 | — (uncommitted) | **Sprint 9.5 Ads v2 — implementation (9.5.1–9.5.8).** New: `migrations/versions/202606240001_ads_v2_schema.py`; `domain/enums/{ad_placement,ad_audience}.py` (+widened `ad_type`); `infrastructure/database/models/{ad_button,ad_audience_rule,audience_segment}.py`; `infrastructure/database/repositories/{ad_button,ad_audience_rule,audience_segment}.py`; `services/audience_service.py`; `tests/unit/{test_audience_service,test_ad_service_v2}.py`. Updated: `domain/protocols/{advertising,repositories}.py`; `services/{ad_service,broadcast_service,download_service}.py`; `infrastructure/telegram/ad_sender.py`; `infrastructure/database/models/{advertisement,broadcast}.py` + repos + `__init__`; `bot/callbacks/factory.py` (per-button `a\|ad\|btn`); `bot/handlers/ads.py` (11 new commands); `bot/main.py` + `workers/{main,broadcast_worker}.py` (wiring); `tests/unit/{_fakes,test_ad_service,test_ad_handler,test_broadcast_worker,test_bot_composition,test_download_service,test_callback_factory,test_enums}.py`; `tests/integration/test_ad_repository.py`; `migrations/planned/{ads_v2_schema.py,README.md}` (now only deferred `ad_events`); docs (`MASTER_PLAN.md`, `COMMANDS.md`, `PROJECT_PROGRESS.md`, `TEST_RESULTS.md`). Migration applied (head `202606240001`). | Sprint 9.5 / 9.5.1–9.5.8 | Implementation agent |
| 2026-06-24 | — (uncommitted) | **Sprint 9.5 Ads v2 — planning/governance only (NO runtime code).** New: `migrations/planned/ads_v2_schema.py` (non-wired skeleton), `migrations/planned/README.md`. Updated (docs): `MASTER_PLAN.md` (§23 Sprint 9.5 spec; §5 D-042–D-045; §13.6 planned settings; §18 EP-19/EP-20; §19.3 roadmap; §9 AdHandlers/TelegramAdSender cards from Sprint 9); `PROJECT_PROGRESS.md` (overview row + Sprint 9.5 detail + this log + handoff). Updated (tooling): `pyproject.toml` + `mypy.ini` (exclude `migrations/planned` like `migrations/versions`). No schema/migration applied; Alembic head unchanged (`202606230002`); no settings seeded; bot flow untouched. | Sprint 9.5 (planned) | Planning agent |
| 2026-06-24 | — (uncommitted) | Sprint 9 Smart Advertisements. New: `services/ad_service.py`; `domain/protocols/advertising.py`; `infrastructure/telegram/ad_sender.py`; `bot/handlers/ads.py`; `tests/unit/{test_ad_service,test_ad_handler}.py`; `tests/integration/test_ad_repository.py`. Updated: `infrastructure/database/repositories/advertisement.py` (select/increment/CRUD); `domain/protocols/repositories.py` (`AdRepositoryProtocol` methods); `services/download_service.py` (`AdShowProtocol` hook in `_deliver` + `_show_ads`); `bot/callbacks/factory.py` (`pack_ad_click` + `a` action); `bot/main.py` (`ad_service_factory` + ads router + `TelegramAdSender`); `workers/main.py` (AdService injected into the download-service factory; `CallbackSigner`/`TelegramAdSender`); `tests/unit/{_fakes,test_bot_composition,test_callback_factory,test_download_service}.py`; `PROJECT_PROGRESS.md`, `TEST_RESULTS.md` | Sprint 9 / 9.1–9.4 | Implementation agent |
| 2026-06-24 | — (uncommitted) | Owner feedback #21–#24. New: `domain/enums/user_role.py` (`UNLIMITED_ROLES`). Updated: `services/rate_limit_service.py` (Owner bypass in `check_download`); `bot/middlewares/throttle.py` (Owner not throttled); `bot/handlers/download.py` (`_subject_to_free_cap`); `infrastructure/database/repositories/job.py` + `domain/protocols/repositories.py` (`count_active_for_user(within_seconds=…)`); `services/job_service.py` (pass `worker_job_timeout`); `domain/enums/__init__.py`; `tests/unit/{_fakes,test_rate_limit_service,test_job_service,test_download_handler,test_bot_middlewares}.py`; `PROJECT_PROGRESS.md`, `TEST_RESULTS.md` | Post-Sprint-8 feedback #21–#27 | Implementation agent |
| 2026-06-24 | — (uncommitted) | Owner feedback #14–#20 + history carry-over. Updated: `bot/handlers/download.py` (rate-limit `authorize_download` + `single_active`/`_is_free`); `bot/handlers/admin.py` (`/users`, removed denied catch-all); `services/{job_service,download_service}.py` (single-active BUSY + user-cache invalidation); `services/{rate_limit_service,user_service}.py` (`authorize_download`; `list_users`); `services/history_service.py` + `bot/main.py` (settings-driven `history_page_size`; `rate_limit_service_factory` injection); `infrastructure/database/repositories/{job,user}.py` (`count_active_for_user`; staff-excluding audience); `domain/protocols/repositories.py` (`count_active_for_user`); `tests/unit/{_fakes,test_job_service,test_download_handler,test_admin_handler,test_broadcast_service,test_history_service}.py`; `tests/integration/test_admin_repositories.py`; `PROJECT_PROGRESS.md`, `TEST_RESULTS.md` | Post-Sprint-8 feedback #14–#20 | Implementation agent |
| 2026-06-24 | — (uncommitted) | New: `services/broadcast_service.py`; `workers/broadcast_worker.py`; `bot/handlers/admin.py`; `tests/unit/{test_broadcast_service,test_broadcast_worker,test_admin_handler,test_settings_validation}.py`; `tests/integration/test_admin_repositories.py`. Updated: `services/{user_service,settings_service}.py` (`UserStats`/`get_stats`/`find`; `SettingView`/`list_all`/`set_validated`/`InvalidSettingValueError`); `domain/protocols/repositories.py` (User stats+audience methods, BroadcastRepository methods, SettingsStore `list_all`); `infrastructure/database/repositories/{user,broadcast,setting}.py`; `bot/main.py` (admin router + settings/broadcast factories + queue injection); `workers/main.py` (BroadcastWorker wiring + `broadcast_chunk_size`); `tests/unit/{_fakes,test_bot_composition}.py`; `PROJECT_PROGRESS.md`, `TEST_RESULTS.md` | Sprint 8 / 8.1–8.2 (8.3 deferred) | Implementation agent |
| 2026-06-24 | `7b18b7f` | New: `services/history_service.py`; `bot/handlers/history.py`; `bot/keyboards/history.py`; `tests/unit/{test_history_service,test_history_handler}.py`. Updated: `services/{job_service,download_service,cache_service}.py` (per-waiter progress map; idempotent fan-out delivery; `add_waiter_progress`/`record_uploaded_file`/`record_delivered`); `bot/callbacks/factory.py` (`r`/`h` actions, `arg` field); `bot/main.py` (`history_service_factory` + router); `bot/handlers/help.py` (`/history`); `domain/protocols/repositories.py` (`DownloadRepositoryProtocol.get_for_user`); `infrastructure/database/repositories/download.py` (`get_for_user`, deterministic `created_at DESC, id DESC` order); `tests/unit/{_fakes,test_job_service,test_download_service,test_callback_factory,test_keyboards,test_bot_composition}.py`; `tests/integration/test_pipeline_repositories.py`; `PROJECT_PROGRESS.md`, `TEST_RESULTS.md` | Sprint 7 / 7.1–7.4 | Implementation agent |
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
| 2026-07-03 | Owner-requested security re-run (post-11.5) | Security (45/45) + bandit (0) + abuse sim (L2 Abuse profile: 9,050 attempts, 0 successful downloads — M-22 holds) + pip-audit | PASS after fix | pip-audit found **7 CVEs in starlette 0.41.3** (finding F-2026-01, see SECURITY_REPORT.md). Fixed same session: `fastapi` 0.115.6→0.139.0, `starlette` pinned explicitly at 1.3.1 (**D-065**, Owner-approved). Post-bump gates: unit suite green, mypy --strict clean (164 app files), import-linter 7/7, `pip check` + pip-audit clean, ruff clean (2-file 11.5 format drift fixed separately in `f39ed4c`). No schema/migration change. |
| 2026-07-01 | Sprint 11.5 / 11.5.1–11.5.12 | Unit (853 collected, 0 fail / 0 error, 114 skipped) + ruff + mypy --strict + import-linter + bandit | PASS | New `test_i18n.py` (22 tests: catalog validation, fallback chain, real-catalog en/ar parity, `{key}`/`{locale}` reserved-placeholder regression guard). All 114 skips are `tests/integration/` + `tests/e2e/` requiring live Postgres/Redis/a sandbox bot — **no Docker/live services running this session**, so these skip cleanly rather than run; not a regression (same suites passed live in prior sessions per the entries below). ruff check + format clean. mypy --strict: 37 errors / 12 files, **all pre-existing** — verified via a clean-cache baseline re-run against the original commit (42 errors / 13 files) plus a per-file `git diff` check confirming 8 of the 12 files are untouched by this sprint and the other 4 (`test_admin_wizard.py`, `test_notification_service.py`, `test_download_handler.py`, `test_history_handler.py`) have only previously-documented gaps (`FakeMessageSender`/`MessageSenderProtocol`; a `PanelStates` re-export + `unpack_panel` arg-type note both confirmed present in the original committed file). import-linter 7/7 contracts kept. bandit 0 (all severities). No schema/migration/new settings key. |
| 2026-06-24 | Sprint 9 / 9.1–9.4 | Unit + Integration (405 total, live pg:15 + redis:7) + all gates | PASS | AdService selection truth table (§16.7: master switch, premium/Owner untargeted exemption, role targeting, post-increment frequency, priority + frequency fall-through, signed click button, best-effort send), CRUD + validation, click tracking; ad handlers (7 owner-only commands + click callback, forged-callback rejection); live-DB impression/click increments + role-ranked candidate select; DownloadService ad hook (post-increment total, per-waiter, retry-safe, failure-isolated). mypy --strict 185 files; import-linter 7 contracts; bandit 0 (all severities); no new deps/schema/migrations. Also re-greened the 4 pre-existing settings integration tests (dev-DB `free_daily_limit` had drifted to 50 from manual `/setting_set`; reset to seeded 10). |
| 2026-06-24 | Sprint 8 / 8.1–8.2 | Unit + Integration (328 total, live pg:15 + redis:7) + all gates | PASS | BroadcastService audience snapshot + filters; BroadcastWorker chunked fan-out, failure isolation, role filter, FIFO pickup; admin handlers (stats/userinfo/ban/unban/settings/setting_set/broadcast) incl. validation + owner-gating + denied catch-all; SettingsService write-path validation (int/bool/json/float); live-DB user aggregate counts + broadcast audience cursor + broadcast lifecycle. mypy --strict 178 files; import-linter 7 contracts; bandit 0; pip-audit no new deps. 8.3 (HTTP API) deferred — API-key/401 check not yet covered. |
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
| ~~OQ-10~~ | ~~Approver for English V1 user-facing copy.~~ **Resolved 2026-07-01 (Sprint 11.5).** English + Arabic, ~250+ keys; copy specified directly by the Owner's own design session for this sprint. | Resolved | — | — |
| OQ-11 | Large-file delivery: accept Telegram's 50 MB bot limit, or stand up a self-hosted Telegram Bot API server (up to 2 GB)? Affects which qualities can actually be sent. | Open question | Sprint 6 | Decide before building delivery. |

Open Questions are the canonical issue board until a real one is set up. Update both this section and `MASTER_PLAN.md` Section 27 when resolving an item.

---

## Session Handoff Log

The newest handoff is at the top. Every session ends with a new entry. Never delete old entries.

### Session Handoff — 2026-07-05 — Sprint 13 Admin Panel Enhancement and Growth Features implemented in full

| Field | Value |
|---|---|
| **Session type** | New sprint kickoff, Owner-authored spec (`SPRINT_13_PLAN.md`/`SPRINT_13_PROMPT.md`, found at the worktree root of `happy-bose-71ed46`). The session itself was launched in a different, freshly-created worktree; asked, the Owner explicitly redirected to `happy-bose-71ed46` before any code was written (this repo's live worktree, confirmed via prior-session memory + `git worktree list` — all others are stale clones). Owner then said "continue, finish all tasks, review at the end" plus one added requirement (animated panel emoji) mid-flight, so all 9 tasks were executed back-to-back with a gate+commit after each, no per-task pause. |
| **Scope decision resolved** | Animated emoji: Telegram's Bot API only allows `<tg-emoji>` custom-emoji entities for bots with a **Fragment-purchased username** — not something obtainable in-session. Presented 3 options; Owner chose "build animation-ready, ship Unicode": every icon now routes through a semantic `ui.emoji(code)` behind an empty `CUSTOM_EMOJI_IDS` map, so filling that map later switches the whole panel to animated icons with **zero screen changes**. Not yet animated — this is a real constraint, not a shortcut. |
| **What shipped** | **13.1** `bot/panel/ui.py` design-system primitives + the emoji layer above (50 tests). **13.2** main-menu live dashboard (`open_panel` signature changed), Statistics/User-detail/Downloads/System screens rebuilt on the new primitives (User-detail is now a `ui.card` profile + metrics block). **13.3** per-platform analytics (`AdminService.get_platform_stats`/`get_platform_report`) + a sparkline sub-screen + owner-only CSV export. **13.4** `UserStats` gains active-24h/7d/30d, inactive-5d/7d/30d, hourly cohorts. **13.5** `bot_blocked`/`is_deleted`/`status_checked_at` (migration `202607050001`) + `services/user_health.py::UserHealthChecker` (framework-free via an injected `ChatProber` protocol) + a bot-layer `AiogramChatProber` (aiogram exception → outcome mapping lives here, not in services) + a session-owning `UserHealthStoreAdapter`; Moderation gained Check-Status / Blocked-list / Deleted-list / Purge. **13.6** `UserService.export_users`/`import_users` (CSV/JSON, create-only) + a format-picker screen + an `import_subscribers` FSM upload flow. **13.7** migration `202607050002` (`referrals` table + 3 new `users` columns) + `ReferralService` (unique codes, stacking rewards, dashboard/leaderboard) + `/start ?start=ref_CODE` deep-link + referrer notify + `/referral` command + admin section `r`. **13.8** migration `202607050003` (`message_templates`) + `TemplateService` wired as a process singleton via a new `MessageTemplateStore` adapter, with a transparent override hook added to `core/i18n.py::translate()` (custom text overrides the shipped default with zero caller change) + admin section `tp` (list/edit/reset). **13.9** all of the above registered in `bot/panel/registry.py` (new sections `r`/`tp`, submenu extensions on `t`/`u`/`m`, new read-tier actions `lsb`/`lsd`), two new FSM states, `bot/main.py` composition-root wiring (`referral_service_factory`, `template_service` singleton + startup `.load()`, `health_checker_factory(bot)` resolving the bot's own `@username` via `get_me()`), and every new i18n key added to **both** `en.json`/`ar.json`. |
| **Live-DB incident found + fixed** | Mid-session the Owner started the live bot and hit `asyncpg.exceptions.UndefinedColumnError: column users.bot_blocked does not exist` — the dev Postgres was still on migration `202606270002`, one set behind the new model columns. Not a code bug: ran `alembic upgrade head` (→ `202607050003`) and verified via direct query that the new `users` columns, the `referrals`/`message_templates` tables, and the two seeded referral settings all landed. Bot now boots clean. Lesson recorded for next time: run `alembic upgrade head` after pulling any model change, before starting the bot. |
| **Validation** | Full `tests/unit` suite green (exit 0, no failures) re-verified after every one of the 18 feature commits and again at the end. ruff + format clean throughout. mypy --strict: **0 issues, 174 source files**. import-linter: **7/7 contracts kept** at every commit — both new layer-sensitive pieces (the aiogram-free health checker + the two session-owning DB-store adapters) were deliberately designed to hold `services`/`infrastructure`'s existing boundaries via protocol satisfaction, not by weakening a contract. |
| **Docs updated** | This file (Current Project State, Sprint Overview — **new Sprint 13 row**, new **Sprint 13 detail section** inserted after Sprint 12, this Session Handoff entry). `MASTER_PLAN.md` / `project_reference.md` **not** touched this session — flagging for the Owner/next agent: Sprint 13 has no MASTER_PLAN section yet (unlike every prior sprint, which gets one, e.g. §23 for 11.5); worth adding if this sprint is ratified. |
| **Commits** | 18 feature commits `cecc297`..`3e90c8d` (one per task/sub-slice, each gated: ruff, mypy --strict, full unit suite, import-linter, before commit) + 1 chore `0c523d3` (untracked `graphify-out/` generated artifacts that a background hook's `git add -A` accidentally swept into the `4989ab2` commit; added to `.gitignore`). All on branch `claude/happy-bose-71ed46`. **Not pushed** — push is gated on an explicit ask per standing session rule, and wasn't requested this session. |
| **Still open / not done** | Owner sign-off on Sprint 13 (code/tests complete, not yet reviewed live in full — the Owner did start the bot mid-session and confirm it boots post-migration, but did not walk every new screen). Residual 13.2 cosmetic polish: user-list rows, moderation banned list, errors/jobs lists, ads list/detail, settings grouping, and the broadcast screen still use pre-13.2 formatting (functional, just not yet passed through `ui.py`). Animated emoji genuinely blocked on the Owner obtaining a Fragment bot username + custom-emoji ids. Everything from before Sprint 13 remains open exactly as it was (Sprint 12 Phase A remainder, Phase B infra blockers, S9/S9.5/S10 sign-offs, Owner req #11) — untouched this session. |
| **Notes for the next agent** | Read `SPRINT_13_PLAN.md` (still at the worktree root) for the full design-system spec and screen mockups before touching any panel screen. `bot/panel/ui.py` is now the **only** place panel text formatting should happen — never hand-roll emoji/spacing/tables in a handler again. All 6 new features have both a backend (repo/service/migration, independently tested with fakes) and a front-end (registry/keyboard/handler, wired into the composition root) — if asked to extend one, both layers already exist and follow the existing factory-per-session-vs-singleton pattern (`TemplateService` is the one process singleton; everything else is a per-request factory). `translate(key, locale, **kwargs)` reserves `key`/`locale` as its own arg names — a catalog placeholder must never be named `{key}` or `{locale}` (this bit Sprint 11.5 too; the Sprint 13 template-edit screen uses `{template}` for exactly this reason). Always add a new i18n key to **both** `en.json` and `ar.json` in the same edit — `core.i18n.configure`'s reference-catalog invariant fails startup on an orphaned key, so a missed Arabic translation is caught immediately, not silently. |

### Session Handoff — 2026-07-01 — Sprint 11.5 Internationalization (i18n) implemented in full (pulled forward from V2)

| Field | Value |
|---|---|
| **Session type** | Continuation of the Sprint-12-kickoff session (same day). The Owner asked to continue toward Sprint 12 but then supplied a full localization spec; asked directly, chose to build it now rather than wait for V2. Design went through 3 rounds of Owner simplification during review (captured in MASTER_PLAN D-061–D-064), then a full mechanical implementation across ~30 production files + 14 test files. |
| **Design evolution (for context)** | Round 1: replaced an original first-contact language-picker-gate idea with "default to English immediately, change anytime via a button." Round 2: dropped the `/language` command and the "store supported languages in `settings`" idea in favor of filesystem-discovered catalogs (drop in a JSON file = new language). Round 3 (this session, continuing from an approved plan): implementation + verification, including finding and fixing a real bug (see below). |
| **What shipped** | `core/i18n.py` (catalog loader: discovery, `_meta` validation, default-locale-as-reference-catalog invariant, never-raises `translate()`); `core/locales/{en,ar}.json` (~250+ keys each); `Settings.default_locale` (`DEFAULT_LOCALE` env var); `users.language` reused as the **only** UI-locale field (**no migration** — D-061); `UserFacingError.translation_key`; `UserService.set_language`; new `LocaleMiddleware`; a permanent "🌐 Change Language" entry point (inline button on `/start` for regular users, a new admin-panel section for Owner/Moderator) sharing one signed callback action (`l`) and one apply path; `NotificationService` + fan-out (`DownloadService`/`JobService`) resolve **each recipient's own** locale, not one job-level locale; **every** hardcoded string in the regular-user surface *and* the entire admin panel (registry, keyboards, handlers, compose wizard) now routes through `translate(key, locale, **kwargs)`. |
| **Real bug found + fixed** | `translate(key: str, locale: str, **kwargs)`'s own first parameter is named `key` — a catalog template using `{key}` as its own placeholder collided with any caller passing `key=...` (`TypeError: got multiple values for argument 'key'`), caught by a real test failure in the admin `/setting_set` command. Fixed by renaming the placeholder to `{setting_key}` in both catalogs + the two call sites; added a permanent regression test in `test_i18n.py` that scans every real catalog value for the `{key}`/`{locale}` reserved names. |
| **Validation** | 853 tests collected, **0 failures / 0 errors**, 114 skipped (all `tests/integration/` + `tests/e2e/` — **no Docker/live Postgres/Redis running this session**, so they skip cleanly; not a regression). ruff + format clean. mypy --strict: 37 errors / 12 files, **all pre-existing**, confirmed via a clean-cache baseline re-run against the original commit (42 / 13 before) plus per-file `git diff` — 8 of the 12 files are untouched by this sprint; the other 4 have only previously-documented gaps. import-linter 7/7 kept. bandit 0. See the Sprint 11.5 detail section above and the new Validation Status Log row for the full breakdown. |
| **Docs updated** | `MASTER_PLAN.md` (new §23 "Sprint 11.5" section inserted between Sprint 11 and Sprint 12; D-061–D-064; §2.4/§3/§9 component cards/§10.2/§10.13/§13.2/§17/§18 EP-3+EP-11/§25.7.1/§27 OQ-10 all updated to stop describing i18n as a V2/future item); `project_reference.md` (§23.2/§23.3 fully rewritten from a stale V2 design sketch to the as-built system — this file had been untouched since the initial bootstrap commit, confirmed via `git log`, so this is a deliberate, narrowly-scoped exception, not a full resync); this file (Current Project State, Sprint Overview — **also corrected two pre-existing stale rows I found in passing: Sprint 11's overview row still said "Not Started, 0%" despite Phase A being complete for days, and Sprint 12's still said "0/7" despite A1 shipping earlier today** — both now reflect reality, with the arithmetic shown so a future reader can re-derive it, new Sprint 11.5 detail section, Files Modified Log, Validation Status Log, Known Issues/OQ-10). |
| **Commits** | **None — everything in this entry is uncommitted in the worktree**, same as the rest of this session's predecessor work. Not asked to commit or push. |
| **Still open / not done** | Sprint 11.5's own live-bot human-verification (Arabic RTL round-trip, confirming only admin-panel chrome changes and never ad/broadcast content, multi-language fan-out) is parked for **Sprint 11 Phase B** (needs the sandbox bot) — not a separate blocker, just riding along with the rest of that phase. Sprint 12 Phase A remainder (A2–A6) resumes next, unaffected by this sprint. Owner req **#11** (daily-limit auto-reset verification) still pending. S9/S9.5/S10 sign-offs still pending. |
| **Notes for the next agent** | Read MASTER_PLAN §23 "Sprint 11.5" first for the full as-built design and D-061–D-064 for the *why* behind each simplification round. `core/i18n.py` and both catalogs are the single source of truth for every UI string — never hardcode a new one in a handler; add a key to **both** `en.json` and `ar.json` (the default/`en` catalog is the reference — an orphaned key in `ar.json` alone fails startup) and watch for the `{key}`/`{locale}` reserved-placeholder trap. `MARKDOWN_REMOVAL_GUIDE.md` remains uncommitted in the worktree (leave unless asked, per the prior handoff). |

### Session Handoff — 2026-07-01 — Sprint 12 kickoff (Phase A: A1 prod compose) + admin-panel action fixes + Statistics enrichment

| Field | Value |
|---|---|
| **Session type** | Sprint 12 kickoff, then an Owner-requested admin-panel bug-fix batch. Sprint 12 proposed with a Sprint-11-style **Phase A (code/docs now) vs Phase B (needs production infra)** split; Owner approved and A1 landed. Then Owner reported broken panel actions + wanted richer Statistics; fixed and pushed. |
| **Sprint 12 — A1 done** | `deploy/docker-compose.prod.yml` (`d06b583`): wires `bot`/`worker`/`api` app containers onto the existing postgres/redis/pgbouncer/uptime-kuma infra (single-host V1 topology, `deploy/README.md` §1). App config via `env_file: .env.production`; infra `DB_*` via `${VAR:?}` interpolation; DB path forced through PgBouncer (D-020); images pinned via `${IMAGE_TAG}` for tag-rollback; self-hosted Bot API (D-040) opt-in behind a `bot-api` profile; only the api port published. Validated with `docker compose config`. **No new app config keys** (all from §13.2 / `.env.example`). |
| **Admin panel fix (`8542e2d`)** | The top-level **Users** (Ban/Unban/Upgrade-Premium/Remove-Premium/Make-Admin/Remove-Admin) and **Moderation** (Ban/Unban) buttons were dead-ends: Users actions hit "Open List…", Moderation actions (section `m`, never routed by `panel_write`) fell through to "This action isn't available yet." **Fix:** each now arms a guided "send the Telegram ID" prompt (`PanelStates.user_action`); the typed id re-enters the same apply/confirm path the per-user detail buttons use (destructive → confirm screen; additive → direct; **owner never targetable**). `panel_write` now routes section `m` writes through `_users_write`. New `on_user_action_input` handler (OwnerFilter). Delivers **Owner req #10**. |
| **Statistics enrichment (`4d675cb`)** | Panel Statistics screen now shows **joined today / last 7 days**, **active today**, **premium**, and **staff** counts alongside totals. Via 4 new `UserRepository` count queries (`count_created_since`/`count_active_since`/`count_premium`/`count_staff`) + `UserStats` cohort fields (default 0). **Pure SELECTs — no schema change, no migration.** Downloads section left as-is per Owner. |
| **Validation** | Full suite green with the documented deselects (**~782 pass / 28 e2e-skipped**); ruff + format clean; mypy --strict **160**; import-linter **7**; bandit **0**. Only red is the known env failure `test_generic_list_paginated_and_delete` (dev PG has >10 accumulated broadcast rows) — not a regression. |
| **Commits (pushed)** | `d06b583` Sprint 12 A1 compose · `8542e2d` panel action fixes · `4d675cb` Statistics enrichment · (this) docs. Branch `claude/happy-bose-71ed46`, **pushed** to origin (`dc8fec4..4d675cb`). |
| **Still open / not done** | Sprint 12 **Phase A remainder** (A2 `.env.production.example`, A3 smoke-test scripts/checklist, A4 release checklist, A5 CI release wiring, A6 runbook drift fix) not yet started. Sprint 12 **Phase B** (actual deploy, Sentry/Kuma, prod smoke, Gate G-8) blocked on Owner infra + **OQ-1** (Sentry) / **OQ-3** (host) / **OQ-5** (alerts chat), and transitively on **Sprint 11 Phase B**. Owner req **#11** (verify daily-limit auto-reset) still pending. S9/S9.5/S10 sign-offs still pend. |
| **Notes for the next agent** | The panel fixes are unit-verified but **not yet live-tested** against a bot. New top-level user actions and Statistics are in `bot/handlers/admin_panel.py`; add user-action verbs in `_USER_ACTION_PROMPT`. `MARKDOWN_REMOVAL_GUIDE.md` remains uncommitted in the worktree (leave unless asked). |

### Session Handoff — 2026-06-27 — Sprint 11 Phase A COMPLETE (11.1–11.9); Phase B (live runs) blocked on Owner infra

| Field | Value |
|---|---|
| **Session type** | Implementation — Sprint 11, full Phase A. Owner directive: "continue all the sprint without stop." Proceeded through every code-able task, committing each with all gates green; stopped only at the genuine Phase-B boundary (no live sandbox/infra) rather than fabricating capacity numbers. |
| **Done (Phase A, 9 tasks)** | **11.1** isolation (`DEPLOY_ENV`+fingerprint, D-060, `core/environment.py` rule registry). **11.5** security suite — all 5 §25.9 categories (`tests/security/…`, 45 tests). **11.6** simulation framework (`tests/simulation/`: `SimulationRunner`+CLI, `StubBotClient`, `MetricsCollector`/`RunSummary`, `ReportWriter`, prod-credential rejection). **11.7** five profiles (Casual/Active/Heavy/Abuse; Premium disabled). **11.8** five traffic generators. **11.9** stress catalog ST-1…ST-6. **11.2** E2E harness + `harness` fixture. **11.3** E2E flow suites (§25.7). **11.4** named scenarios S-1…S-5. |
| **Validation (cumulative)** | **766 pass / 28 skipped (E2E Phase-B-gated) / 0 fail / 2 deselected**; ruff + format clean; mypy --strict **160** (tests excluded from the strict gate by design); import-linter **7**; bandit **0**. No schema change, no migration, **no new dependency**. CLI verified: `python -m tests.simulation.runner --level=L1..L4` runs to completion deterministically; Abuse → **0 successful downloads** (M-22). |
| **Phase B — NOT done (needs Owner infra)** | 11.10 real load L1–L4, 11.11 stress ST-1…6 (esp. fault-injection ST-3/4/5/6), live E2E S-1…S-5 execution, 11.13 capacity numbers, 11.14 M-17/18/19/20. All require the @BotFather **sandbox bot** + isolated **test PG/Redis/storage**, then `DEPLOY_ENV=test` + `E2E_LIVE=1`. A clearly-labelled **stub dry-run** of L1–L4 + a capacity-methodology stub are in `PERFORMANCE_REPORT.md` (explicitly *not* capacity numbers). |
| **Commits (this session)** | `4ac5f0b` 11.1 · `de0e9d3` 11.5 · `cacfaa6` 11.6 · `199366e` 11.7 · `1b1a1a0` 11.8 · `e83ad78` 11.9 · `14816d0` 11.2–11.4 · (this) 11.10-partial + reports. Worktree `happy-bose-71ed46`, branch `claude/happy-bose-71ed46`, parent `066b43a`. Not pushed. |
| **Gate** | 11.1 + 11.5 touch security/isolation config → **Gate G-5** awaiting Owner `Gate G-5 approved`. |
| **Owner action** | (1) sign off **Gate G-5**; (2) provision the Phase-B sandbox bot + test infra to run 11.10–11.14 live; (3) the sprint cannot fully close (DoD/Exit) until the live runs + capacity sign-off land. Pre-existing S9/S9.5/S10 sign-offs + 9.5.9/9.5.10 verification still pend. |
| **Notes for the next agent** | `tests/simulation/` is NOT a pytest collection root (framework); self-tests live in `tests/unit/`. The live `SandboxBotClient` (simulation) and `E2EHarness.connect` (e2e) are the two Phase-B implementation seams. Add isolation rules via `core/environment.ENVIRONMENT_SAFETY_RULES`; profiles via `@register_profile`; generators via `@register_generator` — no engine edits. |

### Session Handoff — 2026-06-27 — Sprint 11 kickoff: Task 11.1 (test-environment isolation) complete

| Field | Value |
|---|---|
| **Session type** | Implementation — Sprint 11 (Testing, Security & Load Framework) start. Owner approved the breakdown + a **code-first / defer-live-runs** phasing and chose **11.1** as the first checkpoint. |
| **Scope decisions** | Live runs (E2E execution, load L1–L4, stress ST-1…6, capacity, manual M-17…22) are **Phase B**, deferred until the Owner provisions a @BotFather sandbox bot + isolated test PG/Redis/storage. Phase A is framework code, built + gated now. Worktree confirmed: **`happy-bose-71ed46`** (this session physically ran in `nostalgic-heyrovsky-e17d8d` but all edits/commits target happy-bose). Push only on Owner request. |
| **What changed (11.1)** | Two LOCKED §13.2 env keys added (Owner-approved, **D-060**): `DEPLOY_ENV` (`development`/`test`/`production`, default `development`) + `PROD_BOT_TOKEN_FINGERPRINT` (SHA-256 hex of the prod token — a one-way hash, not a secret). New `core/security.py::token_fingerprint`. New **extensible** `core/environment.py`: `EnvironmentSafetyRule` + `ENVIRONMENT_SAFETY_RULES` registry + `evaluate_environment_safety` + `EnvironmentMisconfiguredError`. `core/config.py` gained the two fields, a `deploy_env` normalizer, a self-enforcing `_enforce_environment_safety` model-validator, and `is_test_env`/`is_production` props. First rule (D-032): refuse to boot `DEPLOY_ENV=test` against the production bot. `.env.example` updated. |
| **Why the registry** | Owner refinement: keep the validation generic so future isolation rules (test must not use a production DB/Redis/storage/webhook) register without touching the startup architecture. Rules are run by one model-validator, so every current + future entry point inherits them. |
| **Validation** | **691 pass** (671 → +20) / 0 fail / 2 deselected (documented env gotchas). ruff + format clean; mypy --strict **160** files; import-linter **7** contracts; bandit **0**. No schema change, no migration, no new dependency. First occupant of `tests/security/`. |
| **Gate** | Touches security/isolation configuration → **Gate G-5** (Security configuration). PR must carry `Gate G-5 approved` before merge. |
| **Commits** | (this commit) Sprint 11 Task 11.1. Worktree `happy-bose-71ed46`, branch `claude/happy-bose-71ed46`, parent `066b43a`. |
| **Owner action** | Review 11.1 + sign off **Gate G-5**. Then approve the next Phase-A checkpoint (recommend **11.5** security suite, or **11.6** simulation skeleton). |
| **Notes for the next agent** | Add new environment safety rules by appending to `core/environment.py::ENVIRONMENT_SAFETY_RULES` — never re-wire the startup path. The fingerprint is `core.security.token_fingerprint(token)` (SHA-256); store only the hash, never a token (Hard Rule 6). `tests/security/` is now live (first file: `test_environment_isolation.py`); 11.5 fills the remaining four §25.9 categories. |

### Session Handoff — 2026-06-27 — Sprint 9.6 Admin Panel: unified audience engine + multi-placement + compose wizard (C1–C9, **COMPLETE — Owner signed off 2026-06-27**)

| Field | Value |
|---|---|
| **Sign-off** | **Sprint 9.6 approved + signed off by the Owner 2026-06-27.** EP-22 (panel) + EP-23 (rich builder) COMPLETE; D-055–D-059 finalized. Includes the Audience-Builder mutual-exclusivity UX fix (`0828dd4`). No "Under Review" items remain for this sprint. |
| **Session type** | Implementation (Sprint 9.6, F-2/EP-22 + F-3/EP-23). Owner-approved design (`DESIGN_9.6_unified_audience_wizard.md`, Rev 3) then a 9-checkpoint build. |
| **What changed** | Earlier 9.6.1–9.6.9 (panel read sections, settings stepper, users/ads actions) were already committed. This session added, per checkpoint: **C1** a pure `evaluate_audience` + a set-based SQL compiler (`audience_query.compile_audience_predicate`) pinned to the Python matcher by a shared truth table (invariant #17). **C2** migration `202606270001` — `audience_expressions` + `audience_rules`, nullable `audience_expression_id` FK on ads + broadcasts, backfill of `ad_audience_rules` (D-055). **C3** broadcasts target by the unified engine: `UserRepository.count/page_for_audience` + `broadcast_audience_predicate` (guards: exclude banned always, staff unless explicitly included), `BroadcastService.create*` accept `audience_mode`+`audience_rules`, `BroadcastWorker` pages by the expression; legacy role+language dual-read. **C4** migration `202606270002` — `ad_placements` join (multi-placement, D-056, dual-read) + admin-only `internal_name`/`internal_notes` (D-058). **C5** registry-driven wizard engine (`bot/panel/wizard.py`, D-059). **C6–C8** the compose wizard UI (`bot/handlers/admin_wizard.py` + wizard keyboards): Type → Audience (multi-select incl./excl. + typed language/user-id) → Placement (ads, multi-select) → Settings → Content (copy/forward or composed text + buttons) → Preview edit-hub → Save; drives existing services only; D-057. **C9** docs (this entry + MASTER_PLAN §5 D-055–D-059, §23 EP-22/EP-23 in-progress, migrations table; COMMANDS; TEST_RESULTS). |
| **Validation** | **669 tests pass** with the documented deselects; ruff + format clean; mypy --strict 158 files; import-linter 7 contracts; bandit 0. Migrations `202606270001`/`202606270002` applied to the dev DB and verified reversible (down/up round-trip). Postgres + Redis were up, so the integration suites (incl. the SQL≡Python truth table) actually ran. |
| **Commits** | `64aa7d3` design doc · `bea901a` C1 · `188fa0f` C2 · `432b044` C3 · `cd49da5` C4 · `37c096c` C5 · `c70ad5e` C6–C8 · (this) C9 docs. Worktree `happy-bose-71ed46`, branch `claude/happy-bose-71ed46`. |
| **Known scope notes** | Ad **delivery** still reads legacy `ad_audience_rules` (the wizard writes rules there via `AudienceService.add_rule`); switching the ad read-path to the unified expression is a later, separate step. Broadcast audience-shortcut buttons (Free/Premium/All/Language) currently just open the wizard at the Audience step rather than pre-selecting. True Edit-existing-ad (load an ad into the wizard) is not built; the wizard is create-focused. |
| **Owner action** | Review C1–C9. Then the two queued Owner reqs remain: **#10** direct user-id input for every user-targeted action; **#11** verify the daily-limit auto-reset (likely already implemented in RateLimit/User services — confirm, don't rebuild). |
| **Notes for the next agent** | The audience semantics live in ONE place per evaluator: Python `services.audience_service.evaluate_audience`, SQL `infrastructure.database.audience_query` — never edit one without the shared truth table (`tests/audience_cases.py`). New audience dimension/placement/wizard-step = register in `bot/panel/registry.py` / `bot/panel/wizard.py`, no engine edit (D-059). |

### Session Handoff — 2026-06-26 — Owner verification of the backlog: 8.3 signed off, unban fix (#35), queue-test clarified

| Field | Value |
|---|---|
| **Session type** | Owner verification + fixes. Owner ran the gate suite + the full 8.3 curl suite; verifying 9.5.9/9.5.10 later. |
| **8.3 verified + signed off** | Owner exercised every `/v1/admin/*` endpoint: auth 404 (key unset) / 401 (missing/wrong) / 200 (valid); `/stats`, `/users` (+`?telegram_id=`), `/users/{id}`, `/jobs`, `/queue`, `/errors`, `/settings` all returned correct data; `POST .../ban` + `.../unban`, `PUT /settings/{key}` → 200/200/400(bad value)/404(unknown key). **Sprint 8 (incl. 8.3) Owner-signed-off 2026-06-26.** |
| **#35 — unban kept ban_reason (FIXED, D-054)** | Owner saw an unbanned user still showing `ban_reason`. `UserService.unban` now clears `is_banned`/`banned_at`/`ban_reason` (was: preserve as audit). Updated `test_unban_clears_ban_fields`. Backfilled 2 already-unbanned rows in the dev DB (`UPDATE users SET ban_reason=NULL, banned_at=NULL WHERE is_banned=false AND …`). Ban history is V3 audit-log scope (§19.3). |
| **Queue test "failure" explained (not a bug)** | `test_concurrent_dequeue_no_duplicates` showed 997/1000 because a live `workers.main` (DownloadWorker) was ZPOPMIN-draining the same shared `queue:jobs` key during the run. The dequeue Lua is atomic and correct; the suite is 531/531 with no worker running. Hardened the test (flush keys first + a "stop the worker before integration tests" note). Same class as the dev-DB-drift gotcha. |
| **Windows note (not a bug)** | The `/ban` curl failed only due to PowerShell quoting of the JSON body with a space (`api test`). `Invoke-RestMethod … -Body '{"reason":"api test"}'` worked (ban set, then unban 200). `TEST_PLAN.md` updated with the Windows-safe form. |
| **Validation** | **531 tests pass** (clean run, no worker). ruff/format clean; mypy --strict 226 files; bandit 0. No new migration. |
| **Notes for the next agent** | Backlog (8.3 + 9.5.9 + 9.5.10) is code-complete; 8.3 signed off; 9.5/9.5.9/9.5.10 + S9 + S10 await Owner sign-off after the Owner's pending 9.5.9/9.5.10 check. **Sprint 11 starts in a NEW session** (see the kickoff prompt the Owner was given). Cache note: the Redis user cache (TTL 30 s) may briefly serve a stale `ban_reason` for a just-unbanned user via the bot's cache-first path; the admin API `find()` bypasses cache and is immediate. |

### Session Handoff — 2026-06-25 — Deferred-backlog Task 9.5.10 (ad scheduling) implemented — backlog COMPLETE (Under Review)

| Field | Value |
|---|---|
| **Session type** | Deferred-backlog (Owner directed: 8.3, 9.5.9, 9.5.10). **All three done.** This entry: 9.5.10. |
| **What was built** | Migration `202606250002_scheduling` (`down_revision=202606250001`): nullable `scheduled_at` on `broadcasts` + `advertisements` + partial index `ix_broadcasts_scheduled`. **Broadcast due-poller:** `BroadcastRepository.get_next_pending(now)` filters NULL-or-due; the existing `BroadcastWorker` loop passes `now=_now()` (no new worker). **Ad gate:** `AdService.maybe_show` skips ads with `scheduled_at > now`. `BroadcastService.create`/`create_from_ad` + `AdService.create`/`edit` accept `scheduled_at` (ad field `none` clears). Commands `--at <ISO>` (`/broadcast`, `/ad_broadcast`) + `scheduled_at=<ISO>` (`/ad_create`, `/ad_edit`). New `core/timeparse.py`. Models + repos + protocols + fakes threaded `scheduled_at`. |
| **Validation** | **531 tests pass** (508 → +23; live pg:15 + redis:7). ruff + format clean; mypy --strict 226 files; import-linter 7 contracts; bandit 0. Migration applied (head `202606250002`); downgrade↔upgrade round-trip verified. |
| **Owner action** | Optional: `/broadcast hi --at <near-future ISO>` → confirm it sends only after the time passes; `/ad_create … scheduled_at=<future>` → confirm the ad doesn't appear until due. Then sign off 9.5.10 (and S9 + S9.5 + S10). |
| **Notes for the next agent** | The whole deferred backlog is now cleared (8.3 + 9.5.9 + 9.5.10). Broadcast scheduling reuses the BroadcastWorker poll loop (idle interval = worst-case scheduling latency). Ad scheduling is a selection-time gate (no poller). Next: **Sprint 11** (testing framework, security, load/stress) — only after Owner sign-off of S9 + S9.5 + S10. Roadmap F-1/F-2/F-3 remain not-started (do not begin without Owner ask). |

### Session Handoff — 2026-06-25 — Deferred-backlog Task 9.5.9 (ad_events analytics) implemented (Under Review)

| Field | Value |
|---|---|
| **Session type** | Deferred-backlog (Owner directed: 8.3, 9.5.9, 9.5.10, checkpointing between each). **This entry: 9.5.9 done.** 8.3 done earlier this session. 9.5.10 next. |
| **What was built** | Promoted `migrations/planned/ads_v2_schema.py` → `migrations/versions/202606250001_ad_events.py` (`down_revision=202606240001`): partitioned `ad_events` (monthly RANGE by `created_at`, no FKs) + `ix_ad_events_ad` / `ix_ad_events_type_created` + rolling 13-month seed; the planned skeleton was removed. `infrastructure/database/models/ad_event.py` (`AdEvent`), `repositories/ad_event.py` (`AdEventRepository.record` / `count_for_ad`), `domain/enums/ad_event.py` (`AdEventType`). **Off-hot-path recording (D-052):** `AdEventRecorderProtocol` (domain port, sync/non-blocking) + `infrastructure/database/ad_event_recorder.py` (`AdEventRecorder` — own session, fire-and-forget `asyncio` task, best-effort). Wired into `AdService` (impression in `maybe_show`, click in `record_click`+`user_row_id`); composition roots `bot/main.py` + `workers/main.py` build the recorder as a process singleton; the bot ad-click handler now passes `user.id`. Partition rollover/retention use the new `RUNTIME_PARTITIONED_TABLES` (baseline `PARTITIONED_TABLES` frozen). |
| **Validation** | **508 tests pass** (497 → +11; live pg:15 + redis:7). ruff + format clean; mypy --strict 223 files; import-linter 7 contracts; bandit 0. Migration applied to dev DB (head `202606250001`); downgrade↔upgrade round-trip verified (ad_events dropped then re-created with 13 partitions). |
| **Owner action** | Optional: enable ads, trigger a delivery + a button tap, then `SELECT event_type, count(*) FROM ad_events GROUP BY 1;` to see impression/click rows accruing alongside the `advertisements` counters. Then sign off 9.5.9. |
| **Notes for the next agent** | Recording is best-effort and **must not** move onto the request session (it owns its own). `ad_events` has no retention settings key, so its partitions are not auto-dropped (V1 analytics; add a key later if needed). Next: **9.5.10** — `scheduled_at` + due-poller so ads/broadcasts can be scheduled. Then stop for Owner review. Do NOT start roadmap F-1/F-2/F-3. |

### Session Handoff — 2026-06-25 — Deferred-backlog Task 8.3 (HTTP admin API) implemented (Under Review)

| Field | Value |
|---|---|
| **Session type** | Deferred-backlog (Owner directed: implement the three parked tasks — 8.3, 9.5.9, 9.5.10 — checkpointing between each). **This entry: 8.3 done.** |
| **Decision gate resolved** | Owner approved (a) adding `ADMIN_API_KEY` to the LOCKED §13.2 set and (b) the **full §20.2 surface** (all 11 endpoints), plus the auth-failure behavior: **404 when the key is unset (router not mounted), 401 when set-but-wrong.** Recorded as **D-051**; §13.2 row + §20.3 reconciliation note added. The §13.2-vs-§20.3 conflict is now resolved. |
| **What was built** | `api/routes/admin.py` — `create_admin_router(...)` returning the `/v1/admin` `APIRouter`: `GET /stats /users /users/{id} /jobs /queue /errors /settings`, `POST /users/{id}/ban /users/{id}/unban`, `PUT /settings/{key}`. `X-API-Key` header via `APIKeyHeader` + constant-time `hmac.compare_digest`; router-level auth dependency; per-request session dependency (commit/rollback). Routes delegate only — `UserService` (stats/users/ban/unban), `SettingsService` (list/`set_validated`/new `get_view`), `QueueService` (depth/active), new `services/admin_service.py` `AdminService` (jobs listing + error browse via narrow `JobReadRepository`/`ErrorReadRepository` protocols). New repo reads `JobRepository.list_recent` + `ErrorLogRepository.list_recent`. `core/config.py` gained `admin_api_key: SecretStr` + `admin_api_enabled`. `api/app.py` accepts an optional `admin_router`; `api/main.py` mounts it only when the key is set. |
| **Validation** | **497 tests pass** (473 → +24; live pg:15 + redis:7). ruff + format clean; mypy --strict **216** files; import-linter **7 contracts** (`api/routes/admin.py` imports services/domain/core only; infra confined to `api/main.py`); bandit **0**. No schema change, no migration (head stays `202606240001`). New env var only. |
| **Owner action** | Optional: set `ADMIN_API_KEY`, run the api process, and `curl -H "X-API-Key: <key>" http://localhost:8080/v1/admin/stats` (200) vs no/wrong key (401) vs key-unset (404). Then sign off Task 8.3. |
| **Architecture notes** | `api/routes/admin.py` deliberately omits `from __future__ import annotations`: its endpoints live in a closure and inject deps via `Annotated[..., Depends(...)]`; stringized annotations would be resolved against module globals only (missing the closure locals) and FastAPI would mis-read them as query params (observed as 422). Eager annotations bind the markers correctly; self-referential pydantic return types are quoted. With a single shared key there is no per-request identity, so §20.2's "(owner only)" markers are "valid-key-only" in V1 (§20.3). |
| **Notes for the next agent** | Backlog continues: **9.5.9** — promote `migrations/planned/ads_v2_schema.py` (`ad_events`) into `migrations/versions/` with `down_revision = 202606240001`, finish the partition pre-create TODO, wire event recording **off** the ad hot path. **9.5.10** — `scheduled_at` column + due-poller for ads/broadcasts. Stop for Owner review after each. Do NOT start roadmap F-1/F-2/F-3. |

### Session Handoff — 2026-06-25 — Sprint 10 Observability and Backup implemented (Under Review)

| Field | Value |
|---|---|
| **Session type** | Implementation (Sprint 10) — Owner directed "start sprint 10" before signing off S9/S9.5 |
| **Active sprint** | 10 — **10.1–10.8 code/ops-complete, `[~]` Under Review.** Stops at the Sprint 10 stop point for Owner verification. S9 + S9.5 remain `[~]` Under Review. Uncommitted in worktree `happy-bose-71ed46`. |
| **Decision gate resolved** | The HTTP/metrics stack was the one real blocker (8.3 was deferred pending FastAPI approval). Owner approved **FastAPI+uvicorn** (HTTP layer) and **prometheus-client** (metrics) → D-049, D-050; deps pinned in `pyproject.toml`; §6.1/§6.2 rows added. Admin API (8.3) + `ADMIN_API_KEY` stay deferred — the three new endpoints are public. |
| **What was built** | **10.1** Sentry `set_component()`/`request_scope()` in `core/sentry.py`; bot middleware tags correlation_id, worker tags job_id. **10.2** `core/metrics.py` (full §15.3 set; ≥30 series; `PROMETHEUS_MULTIPROC_DIR` aggregation) + instrumentation across JobService/DownloadService/DownloadWorker/CacheService/AdService/BroadcastWorker. **10.3** `core/alerting.py` (throttle 1/fp/5 min + processor) + `infrastructure/telegram/alerter.py`, wired into bot+worker. **10.4** `api/` FastAPI process (`app.py`/`readiness.py`/`main.py`) serving health/ready/metrics; `infrastructure/redis/heartbeat.py` (`WorkerHeartbeat`) + worker heartbeat task. **10.5** CleanupWorker full duties via `DbMaintenanceProtocol` + `infrastructure/database/maintenance.py` (partition rollover, retention drops D-015, orphan sweeps) + partitioning helpers + repo `delete_orphaned`. **10.6** PgBouncer verified + **fixed dead `6432` mapping** (`LISTEN_PORT`/`ADMIN_USERS`/`STATS_USERS`). **10.7** restore drill PASS (`deploy/restore-drill-report.md`). **10.8** `deploy/README.md` runbook. |
| **Validation** | ruff + format clean; mypy --strict 212 files; import-linter 7 contracts; bandit 0; **pytest 473 passed** (live pg:15 + redis:7), +28 tests. No schema change / no migration. `alembic` head unchanged at `202606240001`. |
| **Owner action** | Read `deploy/restore-drill-report.md`; approve `deploy/README.md`. Optionally (DSN-configured env): force a CRITICAL log → expect one throttled Telegram alert; raise a test exception in each process → expect Sentry events tagged `component`/`correlation_id`/`job_id`. Then sign off Sprint 10. |
| **Known issues / deferred** | Cross-process metric **counters** need `PROMETHEUS_MULTIPROC_DIR` (shared volume) — that wiring + the api/bot/worker app containers are Sprint 12. `telegram_send_seconds` defined but not yet observed. Sentry/alert checks are DSN-gated (manual). Sentry-webhook → alert path documented as deferred (no inbound HTTP webhook in V1). |
| **Notes for the next agent** | Run gates with `J:/…/.venv/Scripts/<tool>.exe`. The `api/` package keeps infrastructure imports in `api/main.py` only (import-linter contract) — `app.py`/`readiness.py` take probes as injected callables. Metrics call sites use `core.metrics.record_*`/`observe_*` (core import, no wiring). CleanupWorker stays infrastructure-free via `domain/protocols/maintenance.py`. Next: **Sprint 11** (testing framework, security, load/stress) — only after Owner sign-off of S9 + S9.5 + S10. |

### Session Handoff — 2026-06-25 — Owner feedback #28–#31 (quality/size + ad UX) + #32–#34 roadmap

| Field | Value |
|---|---|
| **Session type** | Bug-fix + UX refinement (download pipeline + Ads v2) + roadmap |
| **Active sprint** | Post-9.5 feedback. Sprint 9 + 9.5 remain `[~]` Under Review. Uncommitted in worktree `happy-bose-71ed46`. |
| **#28 — quality mismatch (FIXED)** | Root cause: the quality button only carries `(media_id, format, quality)`, so the worker re-derived the format via a **height cap** with an uncapped `/best` fallback — which could deliver a different/higher quality than displayed. Fix (D-046): `_format_selector` now downloads the **exact `format_id`** offered for the chosen tier (looked up from `media.formats`, served with `provider_format_id` from the metadata cache); the height-capped path is fallback-only and its last branch is also capped (uncapped `/best` removed) so a download can never exceed the selected tier. |
| **#29 — size inaccuracy (FIXED by the same change)** | The displayed size belongs to a specific format; downloading that exact format makes delivered size ≈ displayed size. |
| **#30 — ad attached under media (DONE)** | The post-download ad is sent as a **reply** to the delivered file (`reply_to_message_id`). `FileSenderProtocol.upload`/`send_cached` now return the delivered message id; `DownloadService._deliver` captures it per waiter and passes it through `AdService.maybe_show` → `AdSenderProtocol`. (D-048) |
| **#31 — direct-open buttons (DONE)** | Ad buttons are now Telegram **URL buttons** (tap opens the destination directly, no extra step). `AdButtonSpec` gained `url`; `_build_markup` renders URL buttons. **Trade-off:** URL buttons fire no callback, so per-button click counts are not incremented (impressions still are). `AdButtonSpec.callback_data` is kept for a future redirect-based tracked mode (ties to #32). (D-047) |
| **#32/#33/#34 — roadmap (design-only)** | Added MASTER_PLAN §23 "Future — Ads & Admin roadmap": F-1 quota-unlock sponsored ads (#32, EP-21), F-2 admin inline control panel (#33, EP-22), F-3 rich ad builder FSM (#34, EP-23). #34 note: nearly all rich content is **already** built in 9.5 (all media types, copy-mode, multiple buttons, formatting) — only the step-by-step builder FSM remains. |
| **Validation** | **445 tests pass** (live pg:15 + redis:7). ruff/format clean; mypy --strict 196 files; import-linter 7 contracts; bandit 0. New/updated tests: exact-format-id selector + capped-fallback (`test_ytdlp_provider`), URL-button rendering + reply threading (`test_ad_service`, `test_ad_service_v2`), message-id returns (`test_file_sender`, `_fakes`). |
| **Owner action** | Re-test: pick 480p → receive 480p (and size ≈ shown); see the ad **attached under** the delivered file; tap an ad button → it **opens the link directly**. Note `/ad_stats` clicks stay 0 for URL-button ads (by design, #31). |
| **Notes for the next agent** | The download now honors the exact offered `format_id` — if a platform's `format_id`s are unstable across the display→download window, the height-capped fallback still bounds quality (never exceeds the tier). Click tracking for ads now requires the reserved redirect mode (EP-21), the right home for the #32 quota-unlock "press Open → unlock" metric. |

### Session Handoff — 2026-06-25 — Sprint 9.5 Ads v2 implemented (9.5.1–9.5.8, Under Review)

| Field | Value |
|---|---|
| **Session type** | Implementation (Sprint 9.5 Ads v2) |
| **Active sprint** | 9.5 — **9.5.1–9.5.8 code-complete + tested, `[~]` Under Review.** 9.5.9 (ad_events analytics) + 9.5.10 (scheduling) deferred by design. Sprint 9 also still Under Review (Owner has not yet signed it off; Owner directed implementation to proceed). Uncommitted in worktree `happy-bose-71ed46`. |
| **What was built** | **Schema** (`202606240001`, applied): advertisements ALTERs (placement/delivery_mode/storage_*/parse_mode/audience_mode), `ad_buttons`, `ad_audience_rules`, `audience_segments`+`audience_segment_members`, `broadcasts.advertisement_id`, placement index, §13.6 seed — additive, no backfill (AdService dual-reads legacy ads). **Audience targeting** (`AudienceService`): include/exclude × role/plan/language/user_id/segment, OR-within/AND-across, segment lazy-load; legacy `target_role` fallback. **Multi-button**: `ad_buttons` rendered as a keyboard; per-button signed callback `a\|ad\|btn`; per-button click counts. **Rich content**: document/audio send paths; **copy-mode** via `bot.copy_message` + storage channel. **Placements**: `placement` column + per-placement toggles + placement-aware `maybe_show`. **Ad broadcast**: `BroadcastService.create_from_ad` + `BroadcastWorker` copyMessage branch. **11 new commands**: `/ad_enable /ad_disable /ad_preview /ad_button_add /ad_button_clear /ad_audience /ad_broadcast /ad_segment_create/_add/_remove/_list`. |
| **Validation** | **441 tests pass** (live pg:15 + redis:7). ruff/format clean; mypy --strict 196 files; import-linter 7 contracts; bandit 0. Migration round-trips (downgrade↔upgrade) verified; head `202606240001`. |
| **Owner action** | Verify: create a `target=` or `/ad_audience` ad → confirm only the intended audience sees it; `/ad_preview`; add 2 buttons via `/ad_button_add` → confirm both render + per-button click counts; `/ad_broadcast <id>` → confirm delivery; enable a placement toggle (e.g. `ad_placement_home_enabled`) and confirm a `placement=home` ad appears. Then sign off Sprint 9 + 9.5. |
| **Known issues** | Album ads require `delivery=copy`. Copy-mode depends on a persistent stored source message. Per-placement toggles default new placements OFF (only `post_download` on) — the download flow's ad behavior is byte-for-byte Sprint 9 unless a new placement is enabled. `ad_events` analytics + scheduling deferred. |
| **Notes for the next agent** | `AdService` is the delivery + ad/button CRUD hub; `AudienceService` owns rule/segment CRUD + evaluation. Selection: `list_active_for_placement(placement)` → `AudienceService.matches` (dual-read) → frequency → deliver. `maybe_show` placement default is `post_download`. To add `ad_events` (9.5.9), promote `migrations/planned/ads_v2_schema.py`. The DownloadService post-download hook is unchanged in intent (now passes language/telegram_id/user_row_id). |

### Session Handoff — 2026-06-24 — Sprint 9.5 Ads v2 fully specified (PLANNING ONLY, no code)

| Field | Value |
|---|---|
| **Session type** | Planning / governance (forward design for a future sprint) |
| **Active sprint** | 9 still `[~]` Under Review (unchanged). **Sprint 9.5 (Ads v2) added as `[ ]` Planned (design-complete).** No implementation, no schema change, no config seeded, no bot-flow change. |
| **What was produced** | The complete Sprint 9.5 spec + all required governance artifacts: MASTER_PLAN **§23** Sprint 9.5 section (scope, proposed schema, audience-evaluation semantics, tasks 9.5.1–9.5.10, validation/exit/human-verification, risks, testing); **§5** decisions **D-042** (dual delivery mode fields/copyMessage + storage channel), **D-043** (first-class audience targeting: `audience_mode` + `ad_audience_rules` + segments, supersedes D-004 additively), **D-044** (placement enum + per-placement toggles), **D-045** (broadcast↔ad unification + `ad_events` + deferred scheduling); **§13.6** planned settings (not seeded); **§18** EP-19/EP-20 (monetization/geo hooks); **§19.3** roadmap row. **Migration skeleton** `migrations/planned/ads_v2_schema.py` (+`README.md`) — intentionally **outside** the Alembic `versions/` scan path, so head stays `202606230002`. Tooling: `pyproject.toml`/`mypy.ini` exclude `migrations/planned` (same as `versions`). |
| **Explicit non-actions (per Owner instruction)** | Did NOT implement runtime behavior, modify the bot flow, activate ads, run/seed any migration, or seed any setting. Sprint 9's behavior is byte-for-byte unchanged. |
| **Audience targeting (first-class, as requested)** | Modeled via `audience_mode` (all/include/exclude) + `ad_audience_rules` (effect × dimension role/plan/language/user_id/segment/country × value) + reusable `audience_segments`. Semantics: within-dimension OR, across-dimension AND; exclude covers "all except premium"; explicit user-ids and custom segments are dimensions. Owner/premium exemptions preserved + overridable. Examples A–E (free-only / premium-only / Arabic-only / specific user-ids / all-except-premium) map directly to rule rows. |
| **Owner action** | Review the Sprint 9.5 spec (MASTER_PLAN §23) + D-042–D-045 + the migration skeleton. Approve to schedule for implementation (it slots after Sprint 9 sign-off; can be re-prioritized vs Sprint 10). Separately: still pending your Sprint 9 human-verification + sign-off. |
| **Validation** | Docs + non-wired skeleton only. Re-ran gates after the tooling-config change: ruff/format clean, mypy --strict 185 files, import-linter 7 contracts, pytest 405 passed, bandit 0. `alembic heads` = `202606230002` (unchanged). |
| **Notes for the next agent** | Ads v2 is additive over Sprint 9: `AdService` selection stays the core (audience eval is a new evaluator over a small candidate list), `AdSenderProtocol` gains a `copy_ad` method, buttons become first-class (`ad_buttons`), broadcasts reuse Sprint 8 plumbing via `broadcasts.advertisement_id`. When implementing, promote `migrations/planned/ads_v2_schema.py` into `versions/` (set `down_revision` to the then-current head, finish the two backfill TODOs) and seed the §13.6 keys via that migration. Per-placement toggles default new placements OFF (no surprise ads). |

### Session Handoff — 2026-06-24 — Sprint 9 Smart Advertisements implemented (Under Review)

| Field | Value |
|---|---|
| **Session type** | Implementation (Sprint 9) |
| **Active sprint** | 9 — **9.1–9.4 code-complete, `[~]` Under Review.** Stops here for Owner human-verification + sign-off before Sprint 10. Uncommitted in worktree `happy-bose-71ed46` (branch `claude/happy-bose-71ed46`). 8.3 HTTP API still deferred. |
| **Tasks moved** | Sprint 9 9.1–9.4 all `[x]`; Sprint 9 → `[~]` Under Review (100%). |
| **What was built** | **9.1** `services/ad_service.py` — selection algorithm §16.7 (LOCKED post-increment, D-010): walks active, role-matching candidates highest-priority-first, falls through on a frequency miss, premium **and** `UNLIMITED_ROLES` (Owner) skip untargeted ads (#21), increments impressions on a delivered ad, best-effort (a send failure is logged + swallowed). Admin CRUD + validation. Ports in `domain/protocols/advertising.py` (`AdSenderProtocol`/`AdClickSignerProtocol`/`AdShowProtocol`); repo SQL in `infrastructure/database/repositories/advertisement.py` (+`AdRepositoryProtocol`). **9.2** `bot/handlers/ads.py` owner-only `/ad_create /ad_list /ad_edit /ad_toggle /ad_delete /ad_stats /ad_global` (silent for non-owners, #18); `key=value` arg parser; media `file_id` pulled from attached/replied media. **9.3** `DownloadService._deliver` calls `AdService.maybe_show` for each **newly-delivered** waiter with their post-increment total — never fails the job, never re-shows on retry. **9.4** signed `a|<ad_id>` ad-click callback records the click + hands the user the link (URL buttons fire no callback, so it's a callback button). |
| **Validation** | **405 tests pass** (340 unit + 65 integration, live pg:15 + redis:7). ruff + format clean; mypy --strict 185 files; import-linter 7 contracts; bandit 0 (all severities); no new deps/schema/migrations (the `advertisements` table + `ix_ads_*` indexes shipped Sprint 2). Also reset the dev-DB `free_daily_limit` (had drifted to 50 via manual `/setting_set`) back to the seeded 10, re-greening 4 pre-existing settings integration tests. |
| **Owner action** | Live verify: `/ad_create title=Promo text=Try premium! button_text=Open button_url=https://example.com every=1`; run a download → see the ad; tap the button → `/ad_stats` shows clicks rising. Check `/ad_global off` suppresses ads; a premium user (and you, the Owner) do not see an untargeted ad; a `target=premium` ad shows to premium only. Then sign off Sprint 9 and authorize Sprint 10. |
| **Known issues** | (1) Ad-click is a callback button (not a URL button) because Telegram's `answerCallbackQuery` cannot open arbitrary URLs — the handler records the click then sends the link as a tap-able message. (2) `workers/main.py` imports `bot.callbacks.factory.CallbackSigner` (shared HMAC helper) to sign ad buttons the bot verifies — import-linter permits it for a composition root; flagged for awareness. (3) Media-ad creation needs a `file_id`: attach/reply to the media, or pass `file_id=...`. |
| **Recommended next task** | After Owner sign-off: Sprint 10 Task 10.1 (Sentry wiring) — see §23 Sprint 10. |
| **Notes for the next agent** | Run gates with `J:/TelegramProjectNewCustomer/TelegramBot/.venv/Scripts/<tool>.exe`. The ad selection lives entirely in `AdService.maybe_show`; effective role = `premium` if an unexpired premium grant else `user`; untargeted exemption = `is_premium_active OR role in UNLIMITED_ROLES`. The post-increment total is computed in `DownloadService._deliver` as `user.total_downloads + 1` captured **before** the counter bump. AdService is injected into `DownloadService` as the `AdShowProtocol` port (optional; `None` = no ads). The same `CallbackSigner` secret (bot token) signs ad clicks in the worker and verifies them in the bot. Admin authz is declarative (`OwnerFilter`); never add authz inside a handler. |

### Session Handoff — 2026-06-24 — Owner sign-off Sprint 7 + Sprint 8 → start Sprint 9

| Field | Value |
|---|---|
| **Session type** | Owner sign-off |
| **Active sprint** | **Sprint 7 + Sprint 8 → `[x]` Completed** (Owner: "everything works right now"). Sprint 8's task 8.3 (HTTP admin API) stays **deferred** by Owner choice. **Next: Sprint 9 (Smart Advertisements).** |
| **Signed off** | Sprint 7 (fan-out + history resend), Sprint 8 8.1–8.2 (admin + broadcast), and all hardening rounds #14–#27 (rate-limit enforcement, free single-active cap with stuck-job ageing, Owner-unlimited, broadcast excludes staff, silent-ignore admin, `/users`). Committed through `df530a8` on `claude/happy-bose-71ed46`. |
| **Deferred / future** | **8.3** `/v1/admin/*` HTTP API — needs FastAPI/uvicorn approval + `ADMIN_API_KEY` (§13.2 vs §20.3). **History-UI sprint** — #25 dedup + #26 title-not-platform display need `downloads` schema changes (title/media_id + uniqueness key); #27 instant file_id resend already done. **#22** role-specific tiers — extend `domain.enums.UNLIMITED_ROLES`. |
| **Validation** | 289 unit pass; ruff/mypy --strict (178)/import-linter (7)/bandit (0) green. Integration (52) pending a `docker compose up` re-run (Docker was off) — covers #14 audience + #24 time-bounded job count. Owner accepted via live manual testing. |
| **Recommended next task** | Sprint 9 Task 9.1 — `services/ad_service.py` (selection algorithm, flow §16.7), then 9.2 ad admin commands, 9.3 post-delivery hook in `DownloadService`, 9.4 click-tracking callback. Read MASTER_PLAN §23 Sprint 9 + §16.7 + the `advertisements` schema §10.10 first. |

### Session Handoff — 2026-06-24 — Owner verification feedback fixes #21–#27

| Field | Value |
|---|---|
| **Session type** | Bug-fix / refinement (second Owner verification round) |
| **Active sprint** | 8 — still `[~]` Under Review. Uncommitted in worktree `happy-bose-71ed46`. |
| **What changed (code: #21, #23, #24)** | **#21 Owner is unlimited** — new single-source `domain.enums.UNLIMITED_ROLES = {OWNER}`. `RateLimitService.check_download` returns early for those roles (no daily limit, no cooldown, no maintenance lockout, no cooldown armed); `ThrottleMiddleware` skips the per-minute throttle for them; the download handler's single-active cap (`_subject_to_free_cap`) excludes them. **#24 (serious) stuck "download in progress"** — `JobRepository.count_active_for_user` is now **time-bounded** (`within_seconds`); `JobService.request` passes `settings.worker_job_timeout` (300s) so a job orphaned in QUEUED/PROCESSING (worker down/crashed; no reaper until Sprint 10) **ages out** and stops blocking new downloads. The Redis download lock was already self-healing (600s TTL). **#23 limit-change freshness** — verified: `/setting_set` invalidates the shared settings cache and `authorize_download` reads the live row, so a new `free_daily_limit` takes effect immediately (regression test added). The residual "old limit" feel is the separate **cooldown** timer. |
| **What was recorded (future, no code)** | **#22** role-specific limits (Owner/Admin/Premium/Free) — architecture kept flexible via `UNLIMITED_ROLES`; extend there. **#25** dedup history rows (needs a `downloads` uniqueness key / `media_id` — schema, own sprint). **#26** show media **title** not platform, sort newest-first (needs `downloads.title` or `media_id` join — schema, own sprint). **#27** instant `file_id` resend — **already implemented** by `HistoryService.resend`; locked as a requirement. (See the Sprint 7 History-UX note.) |
| **Validation** | **289 unit tests pass**; ruff + format clean; mypy --strict 178 files; import-linter 7 contracts; bandit 0. ⚠ **Integration suite NOT run** — Docker Desktop off (52 integration skipped). Re-run with `docker compose up` (covers #14 audience + #24 time-bounded `count_active_for_user`). |
| **Owner action** | Live re-test: Owner downloads without any limit/cooldown; after a download finishes, a new one starts (no stuck "in progress"); `/setting_set free_daily_limit 10` is honoured immediately. Bring up Docker and run the full suite. |
| **Known issues** | A free user whose worker is **down** is blocked for up to `worker_job_timeout` (300s) before the stuck-job ages out — acceptable self-healing fallback. Cooldown is separate from the daily limit (by design, 16.5). 8.3 (HTTP API) still deferred. |
| **Notes for the next agent** | The unlimited-role policy lives ONLY in `domain.enums.UNLIMITED_ROLES` — add roles there for #22, never scatter role checks. The single-active cap's anti-stuck window is `count_active_for_user(within_seconds=settings.worker_job_timeout)`; the real fix for orphaned jobs is the Sprint-10 reaper (terminalize jobs past timeout) — until then the window prevents permanent blocks. #25/#26 need schema changes to `downloads` (title/media_id + a uniqueness key) — they belong to the dedicated History-UI sprint. |

### Session Handoff — 2026-06-24 — Owner verification feedback fixes #14–#20

| Field | Value |
|---|---|
| **Session type** | Bug-fix / refinement (Owner manual-verification feedback) |
| **Active sprint** | 8 — still `[~]` Under Review. This round addresses Owner feedback items #14–#20 found during verification. Uncommitted in worktree `happy-bose-71ed46` (also includes the Sprint-7 `history_page_size` carry-over fix). |
| **What changed** | **#14** Broadcast audience excludes Owner/Moderator by default — untargeted (`--role` absent) now targets role `user` only; an explicit `--role` still targets exactly that role (`UserRepository._audience_filters`). **#15** Download daily-limit + cooldown are now **enforced**: `handle_quality_choice` calls `RateLimitService.authorize_download(telegram_id)` (new) which loads the **authoritative DB row** (the cached `UserSnapshot` count was stale) before any work; over-limit → alert, no job. Counter bumps now invalidate the user cache (JobService cache-hit + DownloadService per waiter) so the next read is fresh. **#16** Free users get a **single active download** cap: `JobService.request(single_active=…)` returns `RequestKind.BUSY` if the user already has a non-terminal job (`JobRepository.count_active_for_user`); cache-hit instant resends are unaffected; premium (`single_active=False`) may run concurrent. **#17** Already satisfied — `HistoryService.resend` delivers from the stored `file_id` first (no re-download); recorded, no code. **#18** Unauthorized admin commands are **silently ignored** — removed the "⛔ not permitted" catch-all. **#19** New owner-only `/users` listing (id, @username, name, lang, role, status). **#20** Quality-pick idempotency: same `(media,format,quality)` dedups to DUPLICATE (lock + `active_downloads`); different-media spam for free users blocked by #16. |
| **Validation** | **282 unit tests pass**; ruff + format clean; mypy --strict 178 files; import-linter 7 contracts; bandit 0. ⚠ **Integration suite NOT run** — Docker Desktop was off (Postgres/Redis unreachable; 52 integration tests skipped). The #14 audience SQL is simple + mirrored by the fake, and `tests/integration/test_admin_repositories.py` expectations were updated (untargeted count excludes staff), but **must be re-run with `docker compose up`**. |
| **Owner action** | Re-test live: set `free_daily_limit 1` → a 2nd download is blocked; start a download then immediately try another → "already in progress"; `/broadcast` → Owner does **not** receive it; a normal user's `/ban`/`/broadcast` → no reply; `/users` lists everyone. Bring up Docker and run the full suite to green the integration tests. |
| **Known issues** | Cooldown is armed by `authorize_download` before the cache/single-active branch resolves (per 16.5, on request not success) — benign. Pre-send broadcast confirmation still deferred. 8.3 (HTTP API) still deferred. |
| **Notes for the next agent** | `RateLimitService.authorize_download(telegram_id)` is the download-path entry (loads the fresh row; `check_download(row)` stays for unit tests). The free single-active cap lives in `JobService.request` via `single_active` (handler computes it with `_is_free(user)`); it sits **after** the cache check so instant hits are never blocked. Broadcast staff-exclusion is in `UserRepository._audience_filters` (`_STAFF_ROLES`). Admin authz is silent — there is no denied handler; do not re-add one. |

### Session Handoff — 2026-06-24 — Sprint 7 committed + Sprint 8 (Admin) 8.1–8.2 implemented (Under Review)

| Field | Value |
|---|---|
| **Session type** | Implementation (Sprint 7 commit + Sprint 8) |
| **Active sprint** | 8 — **8.1+8.2 code-complete, `[~]` Under Review; 8.3 deferred.** Sprint 7 committed `7b18b7f`. Uncommitted Sprint-8 work in worktree `happy-bose-71ed46` (branch `claude/happy-bose-71ed46`). |
| **Tasks moved** | Sprint 7 committed (`7b18b7f`). Sprint 8: 8.1 + 8.2 → `[x]`; 8.3 → **deferred** (Owner decision); Sprint 8 → `[~]` Under Review (2/3). |
| **What was built** | **8.1** `BroadcastService.create` (audience snapshot → `pending` row) + `BroadcastWorker` (polls the durable `broadcasts` table, chunked id-cursor fan-out, per-chunk committed counters, failure isolation, completion). **8.2** `bot/handlers/admin.py`: `/stats` `/userinfo` (staff), `/ban` `/unban` `/setting_set` `/broadcast` (owner), `/settings` (staff); authz via `RoleFilter` + a trailing "denied" catch-all. New repo SQL (User stats+audience, Broadcast lifecycle), `UserService.{get_stats,find}`, `SettingsService.{list_all,set_validated}`. |
| **Validation** | **328 tests pass** (276 unit + 52 integration, live pg:15 + redis:7). ruff + format clean; mypy --strict 178 files; import-linter 7 contracts; bandit 0; pip-audit no new deps. No schema/dependency/migration changes. |
| **⚠ Owner decisions pending** | (1) **Task 8.3 (HTTP API) deferred** — needs FastAPI+uvicorn approval (Hard Rule 3: pins + decision-log) **and** `ADMIN_API_KEY` reconciliation (§20.3 names it but it's absent from the LOCKED §13.2 set). (2) **BroadcastWorker polls the table instead of the queue** (deviation from §16.8 wording; V1's RedisQueue has no `worker_kind` dispatch and §11.4 has no broadcast queue key — polling is the only correct V1 path). (3) Carry-over: **Sprint 7 hardcoded `history_page_size`=5**; §13.4 has a seeded `history_page_size`=10 key `HistoryService` should read. (4) The Sprint-7 `downloads` `job_id`/`media_id` deviations still pending. |
| **Remaining work** | Owner human-verification of Sprint 8 (run each admin command; send a broadcast to a test segment). Then decide task 8.3 (FastAPI) and authorize Sprint 9 (Smart Advertisements). |
| **Known issues** | (1) Pre-send broadcast confirmation prompt deferred (`/broadcast` queues immediately + echoes audience count; a Confirm/Cancel step needs a `bcast:draft` Redis key). (2) `main()` entrypoints remain network-bound + unit-uncovered. |
| **Recommended next task** | After Owner sign-off: either implement deferred 8.3 (once FastAPI approved) or Sprint 9 Task 9.1 (`services/ad_service.py`, flow 16.7). |
| **Notes for the next agent** | Run gates with `J:/TelegramProjectNewCustomer/TelegramBot/.venv/Scripts/<tool>.exe`. The BroadcastWorker is wired in `workers/main.py` (polls every `idle_sleep`, chunk size from the `broadcast_chunk_size` setting); it never touches the download `queue:jobs`. Admin services are injected into the dispatcher as workflow-data factories (`user_service_factory`, `settings_service_factory`, `broadcast_service_factory`) + the `queue_service` singleton in `bot/main.py:build_dispatcher`. Admin authz is declarative (`StaffFilter`/`OwnerFilter` in the handler decorators) — never add authz logic inside a handler. `/setting_set` may only update existing §13.4 keys (the set is LOCKED). |

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
