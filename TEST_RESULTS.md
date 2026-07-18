# Test Results

> **Document Status:** LIVE · Append-only test-results SSOT
> **Companion Documents:** `MASTER_PLAN.md` (Section 25), `PROJECT_PROGRESS.md`, `SECURITY_REPORT.md`, `PERFORMANCE_REPORT.md`
> **Last Updated:** 2026-06-25
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
| Unit | 2026-07-01 | PASS (739) | + Sprint 11.5: `core/i18n.py` catalog loader/validation, en/ar parity, `translate()`/`resolve_locale()` fallback chain, language picker + `set_language`, fan-out per-recipient locale | Sprint 1–11.5 |
| Integration | 2026-06-27 | PASS (~80) | **Not run 2026-07-01 — no live Postgres/Redis this session (no Docker daemon); 114 tests skipped cleanly, see below** | Sprint 2–11 |
| Security | 2026-06-27 | PASS (45) | all 5 §25.9 categories: input_validation, authorization, abuse_protection, data_protection (+ env isolation), dependency_scan | Sprint 11 |
| Performance (micro-benchmarks) | — | — | — | (Sprint 11) |
| E2E (Telegram bot) | 2026-06-27 | PASS (5) + 28 SKIPPED | harness self-tests pass; flow/scenario suites skip until Phase-B sandbox (DEPLOY_ENV=test + E2E_LIVE=1). **Not re-run 2026-07-01** (same reason — no sandbox bot this session) | Sprint 11 |
| Regression | 2026-07-01 | PASS (853 collected, 0 fail / 0 error) | Full suite re-verified after Sprint 11.5's handler-signature changes across ~30 production files | Sprint 1–11.5 |

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

### 2026-07-18 (4) — Unit + in-container — Persistent cookie jar, WARP metadata, size-split downloads

| Field | Value |
|---|---|
| Git SHA | this commit; worktree `happy-bose-71ed46` |
| Environment | local (Windows 11, Python 3.13) + live production (`tgbot_bot` / `tgbot_worker`) |
| Suite | unit (full) + a 9-case wrapper self-test executed inside the worker container |
| Triggered by | Owner: fix cookie management (persist rotated cookies with locking), route YouTube metadata over WARP, split downloads by size |
| Total tests | 971 | Passed | 970 | Failed | 1 (pre-existing `test_enums`) | Skipped | 0 |
| New tests | `test_routing.py` rewritten (9: metadata=WARP-only, unprotected=DIRECT, small→WARP, large→PROXY, inclusive 500 MB boundary, unknown size, threshold override, default value); `test_ytdlp_provider.py` (+5: metadata never leaves WARP, small→WARP-native, large→proxy+aria2c, both fallback directions, configurable threshold); `.env.example` gained the 3 new keys to keep the locked env-parity test green |
| Wrapper self-test (in-container, 9 cases) | persistence on success; persistence on rc≠0; exit-code passthrough; truncated jar rejected; no temp-jar leaks; **10 concurrent runs without corruption**; merge keeps auth cookies + applies rotation + adds new; master never shrinks; empty master degrades to a plain run — all PASS |
| Notes | `deploy/ytdlp-wrapper.sh` rewritten: shared flock to snapshot, no lock during the run, exclusive flock for an in-place write-back (bind-mounted file cannot be renamed over), optimistic-concurrency guard. **A first implementation replaced the master with yt-dlp's jar and was measured in production to destroy SID/HSID/SSID/APISID/SAPISID/LOGIN_INFO/`__Secure-1P*`; it was changed to MERGE before final deploy** and re-verified: 25 → 27 cookies, checksum changed, every auth cookie intact. Production checks: routing table (metadata=`['warp']`, 20 MB/500 MB=`['warp','proxy']`, 501 MB/900 MB=`['proxy','warp']`, tiktok=`['direct']`); all three test videos extract via the real provider in both containers (27/11/27 formats), including the Owner's failing link. |
| Linked PR | — |

**Failures (if any)**
- `test_enums.py::test_media_format_values` — pre-existing known failure; untouched.

**Method note**
- Two of my own intermediate diagnostics were invalid and were re-run: `$YTDLP_WARP_PROXY` is not set inside the containers (the app uses its config default), so shell tests passing that variable silently ran DIRECT; and one inline-Python format count was mis-quoted and reported 0 for every video. Egress results in this entry come from runs using the literal `socks5://warp-lb:1080`.

---

### 2026-07-18 (2) — Unit — Bot-check classification + error_logs write path + burst alerts

| Field | Value |
|---|---|
| Git SHA | this commit; worktree `happy-bose-71ed46` |
| Environment | local (Windows 11, Python 3.13) |
| Suite | unit (full) |
| Triggered by | Production incident: YouTube serves a per-video "Sign in to confirm you're not a bot" wall to the flagged proxy egress; with `--ignore-no-formats-error` it surfaced as a misleading "service busy, try again". Also implements the two agreed observability items: persist failures to `error_logs`, alert on failure bursts. |
| Total tests | 961 | Passed | 960 | Failed | 1 (pre-existing `test_enums`) | Skipped | 0 |
| New tests | `test_error_log_service.py` (4); `test_ytdlp_provider.py` +3 (rc=0 metadata-only + wall signature → `VideoUnavailableError`, both apostrophe variants; no signature → stays transient); `test_alerting.py` +3 (`BurstDetector` fire-at-threshold / isolated-failures / re-arm); `test_download_handler.py` +2 (video-unavailable message; failure persisted with user + platform context) |
| Notes | Changes: `domain` (+`ErrorType.VIDEO_UNAVAILABLE`, +`VideoUnavailableError`, `ErrorLogRepositoryProtocol.record`), `infrastructure` (`ytdlp_provider`: extract keeps stderr (dropped `--no-warnings` on extract only), `_run` → `(stdout, stderr)`, bot-check classifier; `ErrorLogRepository.record`), `services/error_log_service.py` (new — first writer to the until-now write-orphaned `error_logs` table; best-effort, never raises), `core/alerting.py` (+`BurstDetector`), `bot/handlers/download.py` (UserFacingError branch + `record_failure` on every failure path + one CRITICAL `analyze_failure_burst` per ≥5-failures/10-min burst → existing Telegram alert pipeline), `bot/main.py` (factory wiring), locales (+`errors.video_unavailable`). Gates: ruff/mypy add **zero** new findings vs HEAD (verified by stash-baseline runs). |
| Linked PR | — |

**Failures (if any)**
- `test_enums.py::test_media_format_values` — pre-existing known failure; untouched.

---

### 2026-07-18 — Unit — Analysis-failure observability + global error backstop

| Field | Value |
|---|---|
| Git SHA | this commit; worktree `happy-bose-71ed46` |
| Environment | local (Windows 11, Python 3.13) |
| Suite | unit (full) |
| Triggered by | Production log review: `analyze_transient_failure` events carried no platform/host, `platform.generic` i18n key missing, no global aiogram error handler |
| Total tests | 949 | Passed | 948 | Failed | 1 (pre-existing, see below) | Skipped | 0 |
| New tests | `test_error_handler.py` (4: message/callback apology + locale pick, apology-failure swallowed, bare update logs only); `test_download_handler.py` +2 (transient-failure log carries `platform`/`url_host`/`url_hash`; unexpected analyzer exception edits the ack to `errors.unexpected` and never propagates); `test_bot_composition.py` updated (9 routers, errors backstop first) |
| Notes | Changes: `bot/handlers/download.py` (`_url_log_fields` — platform + host + 12-char URL hash on `download_requested` / `analyze_unsupported_url` / `analyze_transient_failure` / `analyze_extraction_failed`; catch-all `analyze_unexpected_error` guard), new `bot/handlers/errors.py` (global `update_handling_failed` backstop, localized `errors.unexpected` reply), `bot/main.py` (router wired first), `core/locales/{en,ar}.json` (+`errors.unexpected`, +`platform.generic`). ruff clean on changed files; mypy: no new errors in changed files. |
| Linked PR | — |

**Failures (if any)**
- `test_enums.py::test_media_format_values` — pre-existing known failure (IMAGE member vs stale expected set); not touched by this change.

**Skips (if non-trivial)**
- None.

---

### 2026-07-01 — Unit + full regression — Sprint 11.5 (Internationalization / i18n, 11.5.1–11.5.12)

| Field | Value |
|---|---|
| Git SHA | this session (uncommitted); worktree `happy-bose-71ed46` |
| Environment | local — **no Docker daemon running this session** (`docker ps` fails to connect), so no live Postgres/Redis/sandbox bot |
| Suite | unit (full) + attempted integration/e2e/security (skip cleanly, no live services) |
| Sprint | 11.5 |
| Triggered by | Sprint 11.5 implementation — pulled forward from V2 at Owner direction |
| Total tests | 853 | Passed | 739 | Failed | 0 | Skipped | 114 | Deselected | 0 |
| New tests | `tests/unit/test_i18n.py` (22: catalog `_meta` validation via crafted `tmp_path` catalogs, `translate`/`resolve_locale` fallback + never-writes-back behavior, real en/ar catalog invariants incl. full key parity and the `{key}`/`{locale}` reserved-placeholder regression guard); ~5 new language-picker tests in `test_bot_handlers.py` (open-picker sentinel, pick-persists-and-confirms-in-new-locale, reject-disabled/unknown code, forged-callback rejection) |
| Notes | Every one of the 114 skips is `tests/integration/` or `tests/e2e/` requiring a live Postgres/Redis/sandbox bot this session's environment doesn't have running — **not a regression**; these same suites passed live in the 2026-06-27 entries below. mypy --strict: 37 errors / 12 files, **all pre-existing** — verified via a clean-cache baseline mypy run against the original commit (42 errors / 13 files) and a per-file `git diff` confirming 8 of the 12 files are untouched this sprint; the remaining 4 (`test_admin_wizard.py`, `test_notification_service.py`, `test_download_handler.py`, `test_history_handler.py`) carry only previously-existing gaps (a `PanelStates` re-export note + `unpack_panel` arg-type note both present in the original committed file; `FakeMessageSender` vs `MessageSenderProtocol` missing `parse_mode`, confirmed via `git diff` on `tests/unit/_fakes.py`/`domain/protocols/file_sender.py` showing zero changes). ruff check + format clean. import-linter 7/7 contracts kept. bandit 0 (all severities). No schema/migration, no new settings key — `users.language` (existing, D-022) is the only storage used. A real bug was found and fixed mid-sprint: `translate(key, locale, **kwargs)`'s own `key` parameter collided with a catalog template using `{key}` as its own placeholder (`admin.setting_set.*`); renamed to `{setting_key}` in both catalogs + the two call sites, with a permanent regression test added. |

**Failures:** None. **Skips:** 114 — all integration/e2e tests requiring live Postgres/Redis/a sandbox bot, unavailable in this session's environment (no Docker daemon). Re-run against live infra to get a true integration/e2e result for this sprint's changes (expected to pass unchanged, since no integration-layer code was touched — see the Sprint 11.5 detail in `PROJECT_PROGRESS.md` for the exact file list).

---

### 2026-06-27 — Simulation framework + E2E — Sprint 11 Tasks 11.2–11.4, 11.6–11.9

| Field | Value |
|---|---|
| Git SHA | this commit (Sprint 11 Phase-A framework); worktree `happy-bose-71ed46` |
| Environment | local |
| Suite | unit + e2e (+ full regression) with the documented deselects |
| Triggered by | Sprint 11 Phase-A: simulation framework (11.6–11.9) + E2E harness/suites/scenarios (11.2–11.4) |
| Total tests | 766 | Passed | 766 | Failed | 0 | Skipped | 28 | Deselected | 2 |
| New tests | simulation: `test_simulation_framework.py` (8), `test_user_profiles.py` (5), `test_traffic_generators.py` (9), `test_stress_scenarios.py` (7); e2e: `test_harness.py` (5, run) + 28 flow/scenario tests (skip until Phase B) |
| Notes | `tests/simulation/` is not a pytest collection root (framework); its self-tests live under `tests/unit/`. E2E flow + S-1…S-5 scenario tests are collected and skip cleanly until `DEPLOY_ENV=test` + `E2E_LIVE=1` against the provisioned sandbox (Phase B). CLI verified: `python -m tests.simulation.runner --level=L1 --profile=Abuse --seed=42` → 0 successful downloads (M-22); `--profile=Casual` → downloads succeed. mypy unaffected (tests excluded from the strict gate); bandit 0 (tests excluded). |

**Failures:** None. **Skips:** 28 E2E flow/scenario tests — Phase-B sandbox not provisioned (documented gate, re-enable with `DEPLOY_ENV=test` + `E2E_LIVE=1`).

---

### 2026-06-27 — Security — Sprint 11 Task 11.5 (security suite, all 5 §25.9 categories)

| Field | Value |
|---|---|
| Git SHA | this commit (Sprint 11 Task 11.5); worktree `happy-bose-71ed46` |
| Environment | local |
| Suite | security (+ full unit/integration regression) with the documented deselects |
| Triggered by | Sprint 11 Task 11.5 — security test suite |
| Total tests | 732 | Passed | 732 | Failed | 0 | Deselected | 2 |
| New tests | +41: `input_validation/` (11: malformed/oversized URLs, tampered/forged/oversized callbacks, separator injection), `authorization/` (9: role-gating denials + cross-secret/forged callback rejection), `abuse_protection/` (7: message-rate spam, per-user keying, daily limit, cooldown, ban, owner-exempt), `data_protection/` (7: scrubber + nested + Settings repr + Sentry before_send + substring catalog), `dependency_scan/` (5: exact pins, .env gitignored, no committed .env, pip-audit+bandit CI wiring) |
| Notes | `pip-audit` + `bandit` already wired as CI gates (`.github/workflows/ci.yml`) — verified, not duplicated. Reuses `tests/unit/_fakes.py` doubles. No source change (mypy 160, import-linter 7, bandit 0 unchanged). |

**Failures:** None.

---

### 2026-06-27 — Unit + Integration + Security — Sprint 11 Task 11.1 (DEPLOY_ENV + production-fingerprint boot assertion)

| Field | Value |
|---|---|
| Git SHA | this commit (Sprint 11 Task 11.1); worktree `happy-bose-71ed46`, parent `066b43a` |
| Environment | local (Docker up: postgres:15 + redis:7 + pgbouncer); DB head `202606270002` (no schema change this task) |
| Suite | all (unit + integration + security) with the documented environmental deselects |
| Triggered by | Sprint 11 Task 11.1 — test-environment isolation plumbing |
| Total tests | 691 | Passed | 691 | Failed | 0 | Deselected | 2 |
| New tests | +20 over the 671 baseline: unit `test_security.py` (4: `token_fingerprint`), unit `test_environment.py` (7: rule registry + aggregation + error), unit `test_config.py` (+5: `DEPLOY_ENV` default/normalize/production/invalid/fingerprint-default), security `test_environment_isolation.py` (4: test-vs-prod refuse-boot, sandbox-boots, production-ignores, no-fingerprint-noop) |
| Coverage by path | `core/security.py` `token_fingerprint` (SHA-256); `core/environment.py` safety-rule registry + `evaluate_environment_safety` + `EnvironmentMisconfiguredError`; `core/config.py` `DEPLOY_ENV` Literal + normalizer + `_enforce_environment_safety` model-validator + `is_test_env`/`is_production`. First occupant of the `tests/security/` collection root (§25.2). |
| Notes | Two LOCKED §13.2 keys added (`DEPLOY_ENV`, `PROD_BOT_TOKEN_FINGERPRINT`) — Owner-approved, D-060. `.env.example` updated. No schema change, no migration, no new dependency. Gates: ruff + format clean; mypy --strict 160 files; import-linter 7 contracts; bandit 0. Touches security configuration → Gate **G-5** (awaiting Owner sign-off). |

**Failures:** None. (Deselect set unchanged: redis concurrent-dequeue, settings upsert drift, settings_service ignore — all documented environmental gotchas.)

---

### 2026-06-27 — Unit + Integration — Sprint 9.6 unified audience + multi-placement + compose wizard (C1–C9)

| Field | Value |
|---|---|
| Git SHA | `c70ad5e` (C6–C8) + this C9 docs commit; worktree `happy-bose-71ed46` |
| Environment | local (Docker up: postgres:15 + redis:7 + pgbouncer); DB migrated to head `202606270002` |
| Suite | all (unit + integration) with the documented environmental deselects |
| Triggered by | Sprint 9.6 checkpoints C1–C9 (F-2/EP-22 + F-3/EP-23) |
| Total tests | 669 | Passed | 669 | Failed | 0 | Deselected | 2 |
| Coverage by path | audience evaluator (`test_wizard_engine.py` 11 + `test_audience_evaluator.py` 12): navigation/skip-placement/validation/edit-hub + the Python matcher truth table. SQL≡Python (`integration/test_audience_query.py`): the compiler matches the matcher over real Postgres rows for every truth-table scenario + segment + broadcast guards (banned/staff). schema (`integration/test_audience_expression_schema.py` 3): expression/rules round-trip + cascade + SET NULL + backfill. broadcasts (`test_broadcast_service.py` +3, `test_broadcast_worker.py` +1): create with expression, expected_total via count_for_audience, worker pages by expression. multi-placement + metadata (`test_ad_service_v2.py` +4, `integration/test_ad_placements.py` 3). wizard handlers (`test_admin_wizard.py` 12): start/type/toggles/typed input/content capture/save ad+broadcast/validation-jump/cancel. |
| Notes | Deselect set unchanged (redis concurrent-dequeue, settings upsert drift, settings_service ignore). Migrations `202606270001` + `202606270002` applied + reversible. No new dependency / env var / settings key. Gates: ruff + format clean; mypy --strict 158 files; import-linter 7 contracts; bandit 0. |

**Failures:** None. (Heed the documented gotchas: dev-DB `free_daily_limit` drift and a live worker draining the shared queue both cause non-regression reds — see the deselect set.)

---

### 2026-06-25 — Unit + Integration — Task 9.5.10 (ad/broadcast scheduling, deferred-backlog)

| Field | Value |
|---|---|
| Git SHA | (uncommitted working tree in worktree `happy-bose-71ed46`) |
| Environment | local (Docker up: postgres:15 + redis:7 + pgbouncer); DB migrated to head `202606250002` |
| Suite | all (unit + integration) |
| Triggered by | Deferred-backlog Task 9.5.10 — `scheduled_at` + due-poller |
| Total tests | 531 | Passed | 531 | Failed | 0 | Skipped | 0 |
| Coverage by path | timeparse (`test_timeparse.py`, 5): trailing-Z/naive/offset/date-only parsing + malformed raises. scheduling (`test_scheduling.py`, 9): AdService gate (future not shown / past+unscheduled shown), ad `scheduled_at` field on create (parse + reject bad) and edit (clear), BroadcastService threads `scheduled_at` for plain + ad broadcasts. due-poller (`test_broadcast_worker.py`, +2): future-scheduled broadcast not handled, past-scheduled handled. handlers: `/broadcast --at` schedules + invalid `--at` rejected (`test_admin_handler.py`, +2); `/ad_broadcast --at` schedules (`test_ad_handler.py`, +1). integration (`test_admin_repositories.py`, +1): `get_next_pending(now)` skips not-yet-due, returns immediate, then returns the scheduled one once its time passes. |
| Notes | +23 tests over Task 9.5.9's 508. New migration `202606250002_scheduling` (two nullable columns + partial index); downgrade↔upgrade round-trip verified. New `core/timeparse.py`. No new env var / settings key. Gates: ruff + format clean; mypy --strict 226 files; import-linter 7 contracts; bandit 0. |

**Failures:** None.

---

### 2026-06-25 — Unit + Integration — Task 9.5.9 (ad_events analytics, deferred-backlog)

| Field | Value |
|---|---|
| Git SHA | (uncommitted working tree in worktree `happy-bose-71ed46`) |
| Environment | local (Docker up: postgres:15 + redis:7 + pgbouncer); DB migrated to head `202606250001` |
| Suite | all (unit + integration) |
| Triggered by | Deferred-backlog Task 9.5.9 — `ad_events` per-event analytics |
| Total tests | 508 | Passed | 508 | Failed | 0 | Skipped | 0 |
| Coverage by path | recorder (`test_ad_event_recorder.py`, 4): fire-and-forget defers the write (nothing written until the loop runs), impression/click field mapping, write-failure swallowed, no-running-loop swallowed. AdService recording (`test_ad_event_recording.py`, 5): delivered ad records impression (user+placement) while the counter stays authoritative; suppressed/premium-exempt record nothing; click records a click event; unknown ad records nothing. Integration (`test_ad_events.py`, 2): live partitioned INSERT routes into the current-month partition + `count_for_ad` by type; row fields persist. Schema (`test_schema.py`): `ad_events` present, partitioned, with both indexes. ad-click handler tests updated to pass the `user` snapshot. |
| Notes | +11 tests over Task 8.3's 497. New migration `202606250001_ad_events` (partitioned, no FKs); downgrade↔upgrade round-trip verified on the live DB. No new env var, no new settings key. Gates: ruff + format clean; mypy --strict 223 files; import-linter 7 contracts; bandit 0. |

**Failures:** None.

---

### 2026-06-25 — Unit + Integration — Task 8.3 (HTTP admin API, deferred-backlog)

| Field | Value |
|---|---|
| Git SHA | (uncommitted working tree in worktree `happy-bose-71ed46`) |
| Environment | local (Docker up: postgres:15 + redis:7 + pgbouncer) |
| Suite | all (unit + integration) |
| Triggered by | Deferred-backlog Task 8.3 — `/v1/admin/*` HTTP API |
| Total tests | 497 | Passed | 497 | Failed | 0 | Skipped | 0 |
| Coverage by path | admin API (`test_admin_api.py`, 18): 404 when `ADMIN_API_KEY` unset (router not mounted), 401 on missing/wrong key, public endpoints need no key, and every §20.2 endpoint over ASGI — `/stats` totals+queue, `/users` list + `?telegram_id=` search, user detail + 404, ban (with reason + audit) / unban / 404, `/jobs` + status filter, `/queue`, `/errors` + type filter, `/settings` list, settings `PUT` ok / unknown-key 404 / invalid-value 400. AdminService (`test_admin_service.py`, 2): UUID→str view mapping + filter pass-through. Config (`test_config.py`, +2): `admin_api_enabled` toggle + key redaction. Integration (`test_admin_repositories.py`, +2): `JobRepository.list_recent` + `ErrorLogRepository.list_recent` newest-first ordering + status/type filters on the live DB. |
| Notes | +24 tests over Sprint 10's 473. New env var `ADMIN_API_KEY` (D-051, added to §13.2). No schema change, no migration (head stays `202606240001`). Gates: ruff + format clean; mypy --strict 216 files; import-linter 7 contracts (`api/routes/admin.py` imports services/domain/core only); bandit 0 (constant-time `hmac.compare_digest` key check). |

**Failures:** None.

---

### 2026-06-25 — Unit + Integration — Sprint 10 exit (Observability and Backup, 10.1–10.8)

| Field | Value |
|---|---|
| Git SHA | (uncommitted working tree in worktree `happy-bose-71ed46`) |
| Environment | local (Docker up: postgres:15 + redis:7 + pgbouncer) |
| Suite | all (unit + integration) |
| Triggered by | Sprint 10 exit (tasks 10.1–10.8) |
| Total tests | 473 | Passed | 473 | Failed | 0 | Skipped | 0 |
| Coverage by path | metrics: registry render (≥30 series), recording helpers, live gauges (`test_metrics`); readiness: all-pass / no-workers / db-failure / timeout (`test_readiness`); api: health 200, ready 200/503, metrics exposition + refresh over ASGI (`test_api_app`); alerting: throttle window + per-fingerprint + critical-only processor (`test_alerting`); heartbeat: beat/count/list + TTL expiry (`test_heartbeat`, integration); cleanup: `partitions_to_drop` selection + `maintain_once` orchestration/isolation (`test_cleanup_maintenance`); orphan sweep: terminal-job `active_downloads`/`job_waiters` removal, live kept (`test_orphan_sweep`, integration). |
| Notes | +28 tests over Sprint 9.5's 445. New Owner-approved deps (D-049/D-050): fastapi 0.115.6, uvicorn 0.34.0, prometheus-client 0.21.1. No schema change, no migration (head stays `202606240001`). Gates: ruff + format clean; mypy --strict 212 files; import-linter 7 contracts; bandit 0. Operational drills outside pytest: PgBouncer `SHOW POOLS` transaction-pooling verified on 6432 (10.6, fixed dead port mapping); backup-restore drill PASS (10.7, see `deploy/restore-drill-report.md`). |

**Failures:** None.

---

### 2026-06-25 — Unit + Integration — Owner feedback #28–#31

| Field | Value |
|---|---|
| Git SHA | (uncommitted working tree in worktree `happy-bose-71ed46`) |
| Environment | local (Docker up: postgres:15 + redis:7) |
| Suite | all (unit + integration) |
| Triggered by | Owner feedback #28 (quality), #29 (size), #30 (ad under media), #31 (URL buttons) |
| Total tests | 445 | Passed | 445 | Failed | 0 | Skipped | 0 |
| Coverage by path | ytdlp_provider: exact-`format_id` selector + height-capped fallback (no uncapped `/best`); ad_service/ad_sender: URL-button rendering + `reply_to_message_id` threading; download_service: capture delivered message id + attach ad as reply; file_sender: `upload`/`send_cached` return message id. |
| Notes | #28/#29 fixed together (D-046): download the exact offered format so delivered quality + size match the display. #31 (D-047): direct-open URL buttons — per-button clicks no longer tracked (impressions unaffected); tracked redirect mode reserved. #30 (D-048): ad replies under the media. #32–#34 added to the roadmap (MASTER_PLAN §23 F-1/F-2/F-3, EP-21–23). Gates: ruff + format clean; mypy --strict 196 files; import-linter 7; bandit 0. |

**Failures:** None.

---

### 2026-06-25 — Unit + Integration — Sprint 9.5 (Ads v2, 9.5.1–9.5.8)

| Field | Value |
|---|---|
| Git SHA | (uncommitted working tree in worktree `happy-bose-71ed46`; follows the Sprint 9 work) |
| Environment | local (Docker up: postgres:15 + redis:7); migration `202606240001` applied |
| Suite | all (unit + integration) |
| Sprint | 9.5 |
| Triggered by | Sprint 9.5 tasks 9.5.1–9.5.8 |
| Total tests | 441 |
| Passed | 441 |
| Failed | 0 |
| Skipped | 0 |
| Duration | ~18 s |
| Coverage by path | services.audience_service: include/exclude truth table across role/plan/language/user_id/segment (OR-within/AND-across) + legacy target_role fallback; services.ad_service: placement-aware selection + multi-button render + copy-mode + per-button click + preview + create/edit validation for the new fields; bot.handlers.ads: 11 new owner-only commands + per-button ad-click; workers.broadcast_worker: ad-broadcast copyMessage branch; infrastructure repos: ad_buttons/ad_audience_rules/audience_segments(+members) live CRUD + broadcast link; bot.callbacks.factory: 4-part `a\|ad\|btn` round-trip. |
| Notes | Schema migration `202606240001_ads_v2_schema` applied; downgrade↔upgrade round-trip verified. Additive-only, no data backfill (AdService dual-reads legacy ads). 9.5.9 (ad_events) + 9.5.10 (scheduling) deferred. Gates: ruff + format clean; mypy --strict 196 files; import-linter 7 contracts; bandit 0. |
| Linked PR | — |

**Failures (if any)**
- None.

**Skips (if non-trivial)**
- None — full integration suite ran against live Postgres + Redis.

---

### 2026-06-24 — Unit + Integration — Sprint 9 exit (Smart Advertisements, 9.1–9.4)

| Field | Value |
|---|---|
| Git SHA | (uncommitted working tree in worktree `happy-bose-71ed46`; follows `ffe4ba3`) |
| Environment | local (Docker up: postgres:15 + redis:7 + pgbouncer + self-hosted bot-api) |
| Suite | all (unit + integration) |
| Sprint | 9 |
| Triggered by | Sprint 9 exit (tasks 9.1–9.4) |
| Total tests | 405 |
| Passed | 405 |
| Failed | 0 |
| Skipped | 0 |
| Duration | ~16 s |
| Coverage by path | services.ad_service: selection algorithm §16.7 (master switch, premium/Owner untargeted exemption, role targeting, post-increment frequency, priority + frequency fall-through, best-effort send) + CRUD/validation + click tracking; bot.handlers.ads: 7 owner-only commands + signed click callback + forged-callback rejection; infrastructure.database.repositories.advertisement: live impression/click increments + role-ranked candidate select + apply_update; services.download_service: ad hook per newly-delivered waiter (post-increment total, retry-safe, failure-isolated); bot.callbacks.factory: `a` ad-click round-trip + tamper rejection. |
| Notes | New `services/ad_service.py`, `domain/protocols/advertising.py`, `infrastructure/telegram/ad_sender.py`, `bot/handlers/ads.py`; new tests `test_ad_service.py`, `test_ad_handler.py`, `test_ad_repository.py`. No schema/dependency/migration changes (the `advertisements` table + `ix_ads_*` indexes shipped Sprint 2). Gates: ruff + ruff-format clean; mypy --strict (185 files); import-linter (7 contracts); bandit (0 issues, all severities). Reset dev-DB `free_daily_limit` 50→10 (seeded value; had drifted via manual `/setting_set`), re-greening 4 pre-existing settings integration tests that were red at the start of this session. |
| Linked PR | — |

**Failures (if any)**
- None.

**Skips (if non-trivial)**
- None — the full integration suite ran against live Postgres + Redis.

---

### 2026-06-24 — Unit — Owner verification feedback fixes (#21–#27)

| Field | Value |
|---|---|
| Git SHA | (uncommitted working tree in worktree `happy-bose-71ed46`; follows `9348917`) |
| Environment | local |
| Suite | unit (integration pending — Docker/infra was down) |
| Sprint | 8 (second verification round) |
| Triggered by | Owner feedback items #21–#27 |
| Total tests | 289 unit passed; 52 integration **skipped** (Postgres/Redis unavailable) |
| Passed | 289 |
| Failed | 0 |
| Coverage by path | services.rate_limit_service: Owner bypass (no limit/cooldown/maintenance, no cooldown armed) + `authorize_download` fresh-row enforcement + missing-user no-op + immediate limit-change visibility; bot.middlewares.throttle: Owner never throttled; bot.handlers.download: `_subject_to_free_cap` excludes Owner; services.job_service: stale stuck job (created >window ago) does not block (time-bounded `count_active_for_user`). |
| Notes | **#21** Owner unlimited via single-source `domain.enums.UNLIMITED_ROLES` (rate-limit + throttle + single-active cap all honour it). **#24** `JobRepository.count_active_for_user(within_seconds=…)` — `JobService.request` passes `worker_job_timeout` (300s) so orphaned non-terminal jobs age out (fixes the stuck "download in progress"). **#23** verified immediate limit changes (settings-cache invalidation + fresh-row read); cooldown is a separate timer. **#22/#25/#26/#27** recorded as future requirements (#22 role-flexible via UNLIMITED_ROLES; #25 dedup + #26 title-not-platform need `downloads` schema changes → own sprint; #27 instant `file_id` resend already implemented). **Integration NOT run** (Docker off): `test_admin_repositories` covers #14 audience; the #24 time bound is unit-tested via the fake and exercised live once infra is up. Gates: ruff, ruff-format, mypy --strict (178), import-linter (7), bandit (0). |
| Linked PR | — |

**Failures (if any)**
- None (unit). Integration not executed (infra unavailable).

**Skips (if non-trivial)**
- All 52 integration tests skipped — Postgres/Redis not reachable.

---

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
