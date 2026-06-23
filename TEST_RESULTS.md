# Test Results

> **Document Status:** LIVE · Append-only test-results SSOT
> **Companion Documents:** `MASTER_PLAN.md` (Section 25), `PROJECT_PROGRESS.md`, `SECURITY_REPORT.md`, `PERFORMANCE_REPORT.md`
> **Last Updated:** 2026-06-23
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
| Unit | 2026-06-23 | PASS (101) | Sprint-4 services + entity 100%; middlewares/handlers/filter 97–100% | Sprint 1–4 |
| Integration | 2026-06-23 | PASS (39) | redis 100%, repos 97.70% | Sprint 2-3 |
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
