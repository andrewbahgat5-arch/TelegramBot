# Test Results

> **Document Status:** LIVE · Append-only test-results SSOT
> **Companion Documents:** `MASTER_PLAN.md` (Section 25), `PROJECT_PROGRESS.md`, `SECURITY_REPORT.md`, `PERFORMANCE_REPORT.md`
> **Last Updated:** 2026-06-24
>
> Append a new entry on every test-suite run. Never edit past entries; corrections get a new entry that references the prior one.

---

## How to use this file

Every entry below is a snapshot of a test run. New runs are added at the **top** of the appropriate section (newest first). Entries reference the git SHA of the code that was tested, the test category, the environment, and the outcome.

If you discover a past entry was wrong (e.g., a test was reported green but the suite was misconfigured), do **not** edit the entry. Add a new entry that links back to the wrong one with an explanation.

---

## Status Summary

| Category | Last Run | Last Result | Coverage | Owner of Suite |
|---|---|---|---|---|
| Unit | 2026-06-24 | PASS (282) | + Owner-feedback fixes #14–#20 (rate-limit enforcement, free single-active cap, broadcast excludes staff, silent-ignore admin, /users) | Sprint 1–8 |
| Integration | 2026-06-24 | PENDING (52) | Audience SQL #14 updated; re-run needed with Docker up (infra was down at fix time) | Sprint 2–8 |
| Security | — | — | — | (Sprint 11) |
| Performance (micro-benchmarks) | — | — | — | (Sprint 11) |
| E2E (Telegram bot) | — | — | — | (Sprint 11) |
| Regression | — | — | — | (each sprint adds rows) |

This summary is the only mutable region of this file. Update its rows whenever a new run lands below.

---

## Entry Template

Copy and adapt for every run.

```
### <Date YYYY-MM-DD HH:MM UTC> — <Category> — <Trigger>

| Field | Value |
|---|---|
| Git SHA | <40-char hash> |
| Environment | local | CI | staging | test |
| Suite | unit | integration | security | performance | e2e | regression | all |
| Sprint | <number> |
| Triggered by | <PR #, manual run, scheduled, sprint exit, release> |
| Total tests | <N> |
| Passed | <N> |
| Failed | <N> |
| Skipped | <N> |
| XFail / XPass | <N> / <N> |
| Duration | <hh:mm:ss> |
| Coverage (overall) | <percentage> |
| Coverage by path | core: X%, domain: X%, services: X%, infrastructure: X%, bot: X% |
| Notes | <anything operationally relevant> |
| Linked PR | <url> |

**Failures (if any)**
- `<test_module>::<test_name>` — <one-line failure summary>; root cause: <…>; resolution: <ticket / commit>.

**Skips (if non-trivial)**
- `<test_module>::<test_name>` — <why skipped>; eligible to re-enable when: <…>.
```

---

## Standing Entries

### 2026-06-24 — Unit — Owner verification feedback fixes (#14–#20)

| Field | Value |
|---|---|
| Git SHA | (uncommitted working tree in worktree `happy-bose-71ed46`; follows `73da095`) |
| Environment | local |
| Suite | unit (integration pending — Docker/infra was down) |
| Sprint | 8 (post-verification feedback) |
| Triggered by | Owner manual-verification feedback items #14–#20 |
| Total tests | 282 unit passed; 52 integration **skipped** (Postgres/Redis unavailable) |
| Passed | 282 |
| Failed | 0 |
| Skipped | 52 (integration auto-skips without infra) |
| Coverage by path | services.job_service single-active cap (BUSY) + cache invalidation on cache-hit counter bump; services.download_service cache invalidation per waiter; bot.handlers.download rate-limit enforcement (authorize_download) + over-limit rejection + single_active wiring; services.rate_limit_service.authorize_download (fresh-row load); bot.handlers.admin /users + silent-ignore (denied catch-all removed); broadcast audience excludes staff (UserRepository._audience_filters). |
| Notes | Addresses: **#14** broadcast excludes Owner/Moderator by default (untargeted → role `user` only; explicit `--role` unchanged); **#15** download daily-limit/cooldown now enforced in `handle_quality_choice` via `RateLimitService.authorize_download` reading the **authoritative DB row** (the cached snapshot's count was stale) + user-cache invalidation on every counter bump; **#16** free-user single-active-job cap in `JobService.request` (`single_active` → `RequestKind.BUSY`; cache hits unaffected); **#18** unauthorized admin commands are silently ignored (removed the "not permitted" catch-all); **#19** new owner-only `/users` listing; **#20** quality-pick idempotency — same `(media,format,quality)` dedups to DUPLICATE (existing lock/active_downloads), different-media spam blocked by #16. **#17** (history instant file_id resend) already satisfied by `HistoryService.resend` — no change. **Integration suite not run** (Docker Desktop off): the audience SQL change is straightforward and mirrored by the fake; `tests/integration/test_admin_repositories.py` expectation updated (untargeted count excludes staff) and must be re-run with infra up. Gates: ruff, ruff-format, mypy --strict (178 files), import-linter (7 contracts), bandit (0). |
| Linked PR | — |

**Failures (if any)**
- None (unit). Integration not executed this round (infra unavailable).

**Skips (if non-trivial)**
- All 52 integration tests skipped — Postgres/Redis not reachable. Re-run with `docker compose up` to validate the #14 audience SQL.

---

### 2026-06-24 — Unit + Integration — Sprint 7 carry-over fix (`history_page_size`)

| Field | Value |
|---|---|
| Git SHA | (uncommitted working tree in worktree `happy-bose-71ed46`; follows Sprint 8 working tree) |
| Environment | local |
| Suite | all (unit + integration) |
| Sprint | 8 (Sprint 7 carry-over) |
| Triggered by | Carry-over fix: `HistoryService` now reads `history_page_size` from `SettingsService` instead of the hardcoded `HISTORY_PAGE_SIZE = 5` |
| Total tests | 330 (278 unit + 52 integration) |
| Passed | 330 |
| Failed | 0 |
| Skipped | 0 (with infra up; integration auto-skips when pg/redis absent) |
| XFail / XPass | 0 / 0 |
| Duration | unit ~6 s; full (unit + integration) ~19 s |
| Coverage by path | services.history_service: page size now read via `SettingsService.get("history_page_size")` (read-through cached, mirrors `RateLimitService`), default-10 fallback on `SettingNotFoundError`, over-read-by-one next-page detection unchanged. New unit tests: `test_list_history_honours_configured_page_size`, `test_list_history_falls_back_to_default_when_unseeded`; `test_list_history_paginates_newest_first` reworked off the removed module constant. |
| Notes | `make_history_service` (bot/main.py) now injects `make_settings_service(session)`. Test harness `_build` seeds a `FakeSettingsStore` + `FakeCache`-backed `SettingsService` (`page_size=None` leaves the key unseeded to exercise the default). **No §13.4 key, schema, or migration change.** Gates: ruff, ruff-format, mypy --strict (178 files), import-linter (7 contracts kept), bandit (0 findings). |
| Linked PR | — |

**Failures (if any)**
- None. (`tests/integration/test_redis_queue.py::test_concurrent_dequeue_no_duplicates` flaked once during the full run — a known concurrency-timing flake against live Redis, unrelated to this change — and passed on isolated re-run and the subsequent full run.)

**Skips (if non-trivial)**
- None when infra is up. The integration suite auto-skips without Postgres/Redis.

---

### 2026-06-24 — Unit + Integration — Sprint 8 exit (Admin and Ops, 8.1–8.2)

| Field | Value |
|---|---|
| Git SHA | (uncommitted working tree in worktree `happy-bose-71ed46`; follows `7b18b7f`) |
| Environment | local |
| Suite | all (unit + integration) |
| Sprint | 8 |
| Triggered by | Sprint 8 exit (in-bot admin surface; tasks 8.1–8.2, 8.3 deferred) |
| Total tests | 328 (276 unit + 52 integration) |
| Passed | 328 |
| Failed | 0 |
| Skipped | 0 (with infra up; integration auto-skips when pg/redis absent) |
| XFail / XPass | 0 / 0 |
| Duration | unit ~5 s; full (unit + integration) ~16 s |
| Coverage by path | services.broadcast_service (audience snapshot, filters, empty/role validation); workers.broadcast_worker (chunked fan-out, failure isolation, role filter, FIFO pickup, idle no-op); bot.handlers.admin (stats/userinfo/ban/unban/settings/setting_set/broadcast incl. usage + not-found + validation + owner-gating + denied catch-all); services.settings_service.set_validated (int/bool/json/float accept + reject + unknown-key); repositories.user aggregate counts + broadcast audience filter/cursor + repositories.broadcast lifecycle via live-DB `test_admin_repositories`. |
| Notes | New unit suites: `test_broadcast_service`, `test_broadcast_worker`, `test_admin_handler`, `test_settings_validation`. New integration suite `test_admin_repositories` (4 tests; audience tests isolate via a unique per-test `language` marker since the shared DB holds the Owner's real users). Updated `test_bot_composition` (5 routers), `_fakes` (broadcast repo, user audience/stats methods, settings `list_all`). **No schema/dependency/migration changes** (`broadcast_chunk_size` uses the existing seeded settings key). Task 8.3 (`/v1/admin/*`) deferred by Owner decision → the "admin API requires API key / 401" checklist item is not yet covered. Gates: ruff, ruff-format, mypy --strict (178 files), import-linter (7 contracts kept), bandit (0 findings), pip-audit (no new deps). |
| Linked PR | — |

**Failures (if any)**
- None. (During development two `test_admin_repositories` audience tests failed against the shared live DB — pre-existing real users matched a generic `language="en"` filter, and an 11-char marker overflowed `language VARCHAR(10)`; fixed by isolating with a unique ≤9-char per-test marker.)

**Skips (if non-trivial)**
- None when infra is up. The integration suite auto-skips without Postgres/Redis.

---

### 2026-06-24 — Unit + Integration — Sprint 7 exit (Fan-Out and Resend)

| Field | Value |
|---|---|
| Git SHA | (uncommitted working tree in worktree `happy-bose-71ed46`; follows `ec157de`) |
| Environment | local |
| Suite | all (unit + integration) |
| Sprint | 7 |
| Triggered by | Sprint 7 exit (fan-out delivery + resend; tasks 7.1–7.4) |
| Total tests | 290 (242 unit + 48 integration) |
| Passed | 290 |
| Failed | 0 |
| Skipped | 0 (with infra up; integration auto-skips when pg/redis absent) |
| XFail / XPass | 0 / 0 |
| Duration | unit ~5 s; full (unit + integration) ~15 s |
| Coverage by path | services.download_service fan-out: deliver-to-all-waiters-once, **retry-after-partial-delivery idempotency** (no re-upload, skip already-delivered), per-waiter-failure isolation, per-waiter completion edits; services.job_service duplicate→waiter-progress-context; services.history_service list pagination + resend (cache-hit no-new-row / evict+requeue / needs-relink / not-found); bot.handlers.history (`/history`, page nav, resend outcomes, forged-ignore); bot.keyboards.history; bot.callbacks resend/page round-trip + tamper; repositories.download `get_for_user` owner-scoping + newest-first pagination via live-DB `test_pipeline_repositories`. |
| Notes | New unit suites: `test_history_service`, `test_history_handler`. Extended: `test_job_service` (per-waiter progress map), `test_download_service` (fan-out + idempotency + failure isolation), `test_callback_factory`, `test_keyboards`, `test_bot_composition` (4 routers), `_fakes` (`FakeDownloadRow.id/created_at`, `get_for_user`). New integration tests in `test_pipeline_repositories`. **No schema/config/dependency/migration changes.** Two schema deviations documented in `PROJECT_PROGRESS.md` Sprint 7 Known Issues for Owner ratification (no `job_id`/`media_id` on `downloads`; idempotency + NULL-cache resend handled at the app/Redis layer). Gates: ruff, ruff-format, mypy --strict (170 files), import-linter (7 contracts kept), bandit (0 findings), pip-audit (no new deps). |
| Linked PR | — |

**Failures (if any)**
- None.

**Skips (if non-trivial)**
- None when infra is up. The integration suite auto-skips without Postgres/Redis.

---

### 2026-06-24 — Unit — Sprint 6 self-healing cache (#13)

| Field | Value |
|---|---|
| Suite | unit (+ full regression) |
| Sprint | 6 (Owner live-test fix) |
| Triggered by | "MP3 not delivered" — cache-hit resends failed with `Bad Request: wrong file identifier` |
| Total tests | 268 (222 unit + 46 integration) |
| Passed | 268 |
| Root cause | **Not MP3 conversion.** The test switched bot tokens; Telegram `file_id`s are bot-scoped, so cached MP3/M4A `file_id`s minted by the old bot were rejected by the new bot. The cache-hit path resent them blindly and failed. |
| Fix | `send_cached` distinguishes invalid-file-id (`CachedFileExpiredError`, new `ErrorType.CACHED_FILE_EXPIRED`) from other Telegram errors; `JobService` delivers from cache first and, on that signal, evicts the stale `cached_files` row + Redis key and falls back to a fresh download. Self-healing across bot rotation, Bot-API endpoint switch, and Telegram expiry. New tests: `test_send_cached_invalid_file_id_raises_cache_expired`, `test_cache_hit_with_invalid_file_id_evicts_and_redownloads`. |
| Gates | ruff, mypy --strict (165 files), import-linter (7), bandit (0), pip-audit (no new deps). The Sprint-3 Redis concurrency tests remain occasionally flaky under parallel load; pass in isolation. |

---

### 2026-06-24 — Unit + Integration — Sprint 6 post-verification fixes

| Field | Value |
|---|---|
| Git SHA | (uncommitted working tree in worktree `happy-bose-71ed46`) |
| Suite | all (unit + integration) |
| Sprint | 6 (Owner live-test fixes) |
| Triggered by | Owner live test surfaced: duplicate delivery, ogg/opus fail+retry-loop, TikTok no-audio, non-monotonic sizes; plus UX asks (instant ack, single progress bar) |
| Total tests | 265 (219 unit + 46 integration) |
| Passed | 265 |
| Failed | 0 |
| Notes | Fixes: deliver via upload-to-user (one file per user); ogg/opus/flac sent as documents + voice extraction; muxed-only sources offer audio; mp4-preferring height-capped selector + `--merge-output-format mp4` so videos play inline; provider-side audio-inclusive sizes (muxed counted once, tbr×duration fallback); instant "Analyzing link…" ack; single-message percentage bar. UX additions: ⬅️ Back button (callback action `b`); title-based sanitized filenames (`_safe_filename`); local Bot API `build_bot` selection unit-verified (`test_telegram_client`). New suites `test_file_sender`, `test_telegram_client`; provider/notification/handler/keyboard/callback regressions updated. Gates: ruff, mypy --strict (165 files), import-linter (7 contracts), bandit (0), pip-audit (no new deps). One Sprint-3 Redis concurrency test (`test_concurrent_dequeue_no_duplicates`) is occasionally flaky under parallel load; passes in isolation. |
| Linked PR | — |

**Failures (if any)**
- None.

---

### 2026-06-24 — Unit + Integration — Sprint 6 exit

| Field | Value |
|---|---|
| Git SHA | (uncommitted working tree in worktree `happy-bose-71ed46`; follows `4b9bf78`) |
| Environment | local |
| Suite | all (unit + integration) |
| Sprint | 6 |
| Triggered by | Sprint 6 exit (Job Pipeline single-user + Owner carry-ins) |
| Total tests | 243 (197 unit + 46 integration) |
| Passed | 243 |
| Failed | 0 |
| Skipped | 0 (with infra up; integration auto-skips when pg/redis absent) |
| XFail / XPass | 0 / 0 |
| Duration | unit ~5 s; full (unit + integration) ~16 s |
| Coverage (overall) | Sprint-6 services/workers covered by 6 new unit suites + 1 integration suite |
| Coverage by path | services.job_service / services.download_service / services.notification_service decision trees + happy/audio/oversize/retry/permanent paths; workers.download_worker (success/retry-requeue/permanent) + workers.cleanup_worker sweep; services.format_extraction audio-expansion + audio-inclusive sizes; repositories.{cached_file,active_download,job_waiter,job,download,user} new methods via live-DB `test_pipeline_repositories`. `infrastructure.telegram.*` / `ffmpeg_client` / `main()` entrypoints exercised by the Owner sandbox run. |
| Notes | New unit suites: `test_job_service`, `test_download_service`, `test_notification_service`, `test_cleanup_worker`, `test_download_worker`, `test_format_sizes`. Updated for D-041/new signatures: `test_download_handler`, `test_format_extraction`, `test_url_analyzer`, `test_bot_composition`, `_fakes`. New integration suite `test_pipeline_repositories` (6 tests) validates PG `ON CONFLICT…RETURNING` + lazy-`CASE` SQL against live postgres:15 — and caught a stale-identity-map bug in `CachedFileRepository.upsert` (fixed with `populate_existing=True`). Gates: ruff, ruff-format, mypy --strict (163 files), import-linter (7 contracts kept), bandit (0 findings), pip-audit (no new deps; tenacity intentionally not vendored — job-level retry used instead). |
| Linked PR | — |

**Failures (if any)**
- None. (During development the live-DB cache-UPSERT test failed once, exposing a real bug; fixed and re-run green.)

**Skips (if non-trivial)**
- None when infra is up. The integration suite auto-skips without Postgres/Redis.

---

### 2026-06-23 — Unit + Integration — Sprint 5 exit

| Field | Value |
|---|---|
| Git SHA | (uncommitted working tree; follows `0e5f301`) |
| Environment | local |
| Suite | all (unit + integration) |
| Sprint | 5 |
| Triggered by | Sprint 5 exit (URL Analyzer + Provider Abstraction) |
| Total tests | 208 |
| Passed | 208 |
| Failed | 0 |
| Skipped | 0 (with infra up; integration auto-skips when pg/redis absent) |
| XFail / XPass | 0 / 0 |
| Duration | unit ~4 s; integration ~10 s |
| Coverage (overall) | Sprint-5 modules ~90% |
| Coverage by path | core.urls 95%, services.url_analyzer 100%, services.format_extraction 100%, infrastructure.downloader.registry 91%, providers.ytdlp_provider ~90%, bot.callbacks 92%, bot.keyboards 94%, bot.handlers.download ~90%; provider_settings via integration |
| Notes | 67 new unit tests + 1 integration. Registry: priority order, failover on `ProviderRetryElsewhere` (DEGRADED at threshold), `ProviderUnsupported` skip, content-error stop, failover-disabled single attempt, cooldown skip/recovery, Redis health persistence. yt-dlp parsing/error-mapping via faked subprocess. Signed callbacks reject tamper/wrong-key/malformed. Gates: ruff, ruff-format (146), mypy --strict (146), import-linter (7 contracts), bandit (0 — removed a B101 assert), pip-audit (no new deps). |
| Linked PR | — |

**Failures (if any)**
- None.

**Skips (if non-trivial)**
- None when infra is up. The integration suite auto-skips without Postgres/Redis.

---

### 2026-06-23 — Unit + Integration — Sprint 4 exit

| Field | Value |
|---|---|
| Git SHA | (uncommitted working tree; follows `de3e7d9`) |
| Environment | local |
| Suite | all (unit + integration) |
| Sprint | 4 |
| Triggered by | Sprint 4 exit (User Identity) |
| Total tests | 140 |
| Passed | 140 |
| Failed | 0 |
| Skipped | 0 |
| XFail / XPass | 0 / 0 |
| Duration | ~00:00:12 |
| Coverage (overall) | Sprint-4 modules 88% (entry-only gap) |
| Coverage by path | services.user_service 100%, services.rate_limit_service 100%, domain.entities.user 100%, bot.middlewares.* 97–100%, bot.handlers.* 100%, bot.filters.role_filter 100%, bot.main 52% (network-bound `main()`/`_run_webhook` only) |
| Notes | 48 new unit tests for Sprint 4. Gates: ruff, ruff-format (124 files), mypy --strict (124 files), import-linter (6 contracts kept; `bot.main → infrastructure.**` composition-root exception holds), bandit (0 findings), pip-audit (clean after orjson 3.11.5→3.11.6). Integration suite (39) ran green against live redis:7 + postgres:15. |
| Linked PR | — |

**Failures (if any)**
- None.

**Skips (if non-trivial)**
- None. (Integration suite auto-skips when Postgres/Redis are unavailable; here both were up.)

---

### 2026-06-23 — Unit + Integration — Sprint 3 exit

| Field | Value |
|---|---|
| Git SHA | (uncommitted working tree; follows Sprint 2 commit 8ccd1e6) |
| Environment | local (Windows 11, Python 3.13.11) + redis:7 + postgres:15 via docker-compose |
| Suite | unit + integration |
| Sprint | 3 |
| Triggered by | Sprint 3 exit checklist |
| Total tests | 92 (53 unit, 39 integration) |
| Passed | 92 |
| Failed | 0 |
| Skipped | 0 (auto-skip only when Redis/Postgres unavailable) |
| Duration | ~13 s |
| Coverage (overall) | `infrastructure/redis` 100% (≥80% exit criterion); `services` 92–100% |
| Notes | Verified: queue priority ordering + FIFO-within-band + 1000-job concurrent dequeue across 3 tasks with zero duplicates; lock acquire/foreign-release-rejection; `SettingsService` read-through cache + write-through invalidation + int/bool/json casts; all Section 11.4 keys emitted by exactly one `RedisKeys` helper. Gates: ruff, ruff-format, mypy --strict (105 files), import-linter (6 contracts), bandit (0), pip-audit (clean). |
| Linked PR | — |

**Failures (if any)**
- None.

**Skips (if non-trivial)**
- None (full stack was up for this run).

---

### 2026-06-23 — Unit + Integration — Sprint 2 exit

| Field | Value |
|---|---|
| Git SHA | (uncommitted working tree; follows Sprint 1 commit 78af6ed) |
| Environment | local (Windows 11, Python 3.13.11) + postgres:15 via docker-compose |
| Suite | unit + integration |
| Sprint | 2 |
| Triggered by | Sprint 2 exit checklist |
| Total tests | 72 (52 unit, 20 integration) |
| Passed | 72 |
| Failed | 0 |
| Skipped | 0 (integration auto-skips only when DB unavailable) |
| Duration | ~7 s |
| Coverage (overall) | `infrastructure/database/repositories` 97.70% (≥80% exit criterion); `infrastructure/database` 97% |
| Notes | Integration tests run against live postgres:15 with per-test transaction rollback. Verified: `alembic upgrade head` → 12 tables, 39 partitions (3×13), 31 indexes, 24 seeded settings, owner user; schema introspection vs Section 10 (columns, FK ON DELETE actions, indexes); repository CRUD + lazy daily reset (D-012) + UUIDv7 job create + partition rollover (fake clock). Gates: ruff, ruff-format, mypy --strict (90 files), import-linter (6 contracts), bandit (0), pip-audit (clean). |
| Linked PR | — |

**Failures (if any)**
- None.

**Skips (if non-trivial)**
- Integration suite skips wholesale when Postgres/migrated schema is unavailable (keeps unit-only/CI-without-DB runs green).

---

### 2026-06-23 — Unit — Sprint 1 exit

| Field | Value |
|---|---|
| Git SHA | (uncommitted working tree; follows Sprint 0 commit 93524d6) |
| Environment | local (Windows 11, Python 3.13.11) |
| Suite | unit |
| Sprint | 1 |
| Triggered by | Sprint 1 exit checklist |
| Total tests | 44 |
| Passed | 44 |
| Failed | 0 |
| Skipped | 0 |
| Duration | ~1.0 s |
| Coverage (overall) | core/ 99.26% branch coverage (`--cov-fail-under=90` satisfied) |
| Coverage by path | core/config 100%, core/logging 100%, core/sentry 100%, core/uuid7 100%, core/constants 100%, core/__main__ 85% (only the `__main__` guard line) |
| Notes | Modules under test: `core/{config,logging,sentry,uuid7,constants,__main__}`, `domain/{exceptions,enums}`. All gates green alongside: ruff, ruff-format, mypy --strict (53 files), import-linter (6 contracts kept), bandit (0 findings), pip-audit (clean). |
| Linked PR | — |

**Failures (if any)**
- None.

**Skips (if non-trivial)**
- None.

---

### 2026-06-23 — Tooling Gates — Sprint 0 exit

| Field | Value |
|---|---|
| Git SHA | (uncommitted working tree) |
| Environment | local (Windows 11, Python 3.13.11) |
| Suite | n/a — configuration/tooling validation only |
| Sprint | 0 |
| Triggered by | Sprint 0 exit checklist (no business tests in scope) |
| Total tests | 0 (empty tree; `pytest` collects 0, exits 0 via `tests/conftest.py` guard) |
| Passed | n/a |
| Failed | 0 |
| Skipped | n/a |
| Duration | < 5 s aggregate |
| Coverage (overall) | n/a (no code under test yet) |
| Notes | Tooling gates all green: `ruff check` ✓, `ruff format --check` ✓ (32 files), `mypy --strict` ✓ (32 files), `lint-imports` ✓ (6 contracts kept), `pytest` ✓ (0 collected, exit 0), `pip-audit` ✓ (no known vulnerabilities — pytest bumped 8.3.5 → 9.0.3 to clear GHSA-6w46-j5rx-g56g), `bandit` ✓ (0 findings across 23 source files). `docker compose config` ✓ (4 services). `docker compose up` not yet run — Docker Desktop daemon was not running on the build host. |
| Linked PR | — |

**Failures (if any)**
- None.

**Skips (if non-trivial)**
- `docker compose up -d` smoke (exit-criteria item) — deferred: Docker Desktop daemon not running on build host; compose file validated via `docker compose config`. Eligible to re-run when: Docker Desktop is started.

---

## Sprint Closeout Snapshots

At every sprint exit, append a sprint-level snapshot here. This makes "what did the project look like at the end of sprint N" answerable without trawling individual entries.

### Template

```
### Sprint <N> Closeout — <Date>

| Field | Value |
|---|---|
| Git SHA at exit | <hash> |
| Sprints completed | <N>/13 |
| Total tests in repo | <N> |
| Aggregate pass rate | <percentage> |
| New tests this sprint | <N> |
| Categories newly active | <list> |
| Regression suite size | <N> |
| Outstanding skips | <N> (linked to issues) |
| Known issues at exit | <list, or "none"> |
```

---

## Release Snapshots

Released versions (V1, V2, …) each get one entry below.

### Template

```
### Release V<X.Y> — <Date>

| Field | Value |
|---|---|
| Git tag | v<X.Y>.<Z> |
| Test summary | unit: pass(N), integration: pass(N), security: pass(N), e2e: pass(N), regression: pass(N) |
| Aggregate coverage | <percentage> |
| Known accepted skips | <list> |
| Sign-off (Owner) | <name + date> |
| Linked Security Report entry | <link> |
| Linked Performance Report entry | <link> |
```

---

> **End of `TEST_RESULTS.md`.** Append-only. Update on every test run.
