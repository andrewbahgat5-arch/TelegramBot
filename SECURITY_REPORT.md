# Security Report

> **Document Status:** LIVE · Append-only security-validation SSOT
> **Companion Documents:** `MASTER_PLAN.md` (Sections 14, 25.9, 25.13), `PROJECT_PROGRESS.md`, `TEST_RESULTS.md`
> **Last Updated:** 2026-07-03
>
> Append a new entry on every security validation run, dependency advisory, incident, or mitigation. Never edit past entries.

---

## How to use this file

Three event types are recorded here:

1. **Validation runs** — outcomes of the `tests/security/` suite, plus `pip-audit`, `bandit`.
2. **Findings** — vulnerabilities discovered (in any category), with severity, status, and mitigation.
3. **Incidents** — security events affecting the running system (after launch).

Entries are append-only. A correction adds a new entry that references the prior one — never edit the original.

---

## Status Summary

| Category | Last Run | Last Result | Open Findings |
|---|---|---|---|
| Input Validation | 2026-07-03 | PASS | 0 |
| Authentication & Authorization | 2026-07-03 | PASS | 0 |
| Abuse Protection | 2026-07-03 | PASS (incl. Abuse-profile sim: 0 successful downloads) | 0 |
| Data Security | 2026-07-03 | PASS | 0 |
| Dependency Security (`pip-audit`) | 2026-07-03 | 1 finding (F-2026-01, starlette) — **FIXED same day (D-065)**; clean post-bump | 0 |
| Dependency Security (`bandit`) | 2026-07-03 | clean (0) | 0 |
| Incidents (since launch) | — | — | 0 |

This summary is the only mutable region. Update its rows after each new entry.

---

## Severity Scale (LOCKED)

| Level | Definition |
|---|---|
| **Critical** | Authentication bypass, RCE, secret leakage at scale, data loss without recovery. Blocks merge / triggers incident response. |
| **High** | Privilege escalation, sensitive data exposure to authorized but wrong users, abuse-protection bypass. Blocks merge. |
| **Medium** | Reduced defense-in-depth (e.g., missing rate-limit on an admin endpoint that requires a key). PR may merge with a tracked issue. |
| **Low** | Hardening opportunities. Tracked, not blocking. |
| **Informational** | Notes for the record. |

---

## Validation Run Template

```
### <Date YYYY-MM-DD HH:MM UTC> — Security Validation Run

| Field | Value |
|---|---|
| Git SHA | <hash> |
| Environment | local | CI | test |
| Sprint | <number> |
| Triggered by | <PR # / scheduled / pre-release> |
| Suites run | tests/security/input_validation, tests/security/authorization, ... |
| pip-audit | clean | <N> findings |
| bandit | clean | <N> findings |
| Total cases | <N> |
| Passed | <N> |
| Failed | <N> |
| Duration | <hh:mm:ss> |
| Linked PR | <url> |

**Findings raised this run (if any)**
- F-NNN — <one-line summary>
```

---

## Finding Template

```
### F-NNN — <one-line title>

| Field | Value |
|---|---|
| Category | input_validation | authorization | abuse_protection | data_security | dependency_security |
| Severity | Critical | High | Medium | Low | Informational |
| Discovered | YYYY-MM-DD — <by suite / tool / human / external> |
| Status | Open | Triaged | Mitigated | Fixed | Won't Fix (with justification) |
| Affected component | <module> |
| Affected versions | <git SHA range> |
| Description | <what the issue is, how it was found> |
| Reproduction | <steps or test_case path> |
| Impact | <what it allows an attacker / abuser to do> |
| Mitigation | <what was done, link to PR, link to TEST_RESULTS.md entry> |
| Owner | <human> |
| Closed | <YYYY-MM-DD or null> |
```

---

## Incident Template

For after-launch security events.

```
### I-NNN — <one-line title>

| Field | Value |
|---|---|
| Discovered | YYYY-MM-DD HH:MM UTC |
| Discovered by | <human / alert / external report> |
| Severity | Critical | High | Medium | Low |
| Status | Open | Contained | Resolved | Post-mortem complete |
| Affected systems | <list> |
| Affected users | <count + characterization> |
| Detection latency | <time from start to discovery> |
| Containment latency | <time from discovery to containment> |
| Full resolution | <time from start to fix deployed> |

**Timeline (UTC)**
- HH:MM — event begins
- HH:MM — first indication
- HH:MM — detection
- HH:MM — containment
- HH:MM — full resolution
- HH:MM — post-mortem complete

**Root cause**
<analysis>

**Mitigation**
<changes deployed>

**Post-mortem outcomes**
- <action items, linked to issues>
```

---

## Standing Entries

### 2026-07-03 — Security Validation Run — Owner-requested full re-run + dependency finding F-2026-01 (FIXED same day)

| Field | Value |
|---|---|
| Git SHA | follows `f39ed4c`; worktree `happy-bose-71ed46` (this commit) |
| Environment | local |
| Sprint | post-11.5 / pre-Sprint-12-Phase-A-remainder (Owner-requested re-run) |
| Triggered by | Owner: re-run Sprint 11 security checks against current code (incl. Sprint 11.5 i18n) |
| Suites run | `tests/security/` all five §25.9 categories + isolation — **45 / 45 passed**; abuse simulation stub (`--level=L2 --profile=Abuse`): 9,050 attempts → **0 successful downloads**, 8,250 blocked (M-22 holds) |
| pip-audit | **RUN LOCALLY — 1 finding (F-2026-01, below), remediated in this same commit; clean after bump** |
| bandit | clean (0 findings, all app packages) |
| Other gates after remediation | unit suite green; mypy --strict clean (164 app files); import-linter 7/7; ruff + format clean (drift in 2 files from 11.5 fixed in `f39ed4c`); `pip check` clean |

**Findings raised this run**

- **F-2026-01 — starlette 0.41.3: 7 known vulnerabilities.** Severity: **High at launch** (starlette is the request-parsing layer of the one internet-facing HTTP surface; prod compose publishes the api port) / **not yet exposed** (no production deploy has occurred). Advisories: PYSEC-2026-161, PYSEC-2026-248, PYSEC-2026-249, GHSA-2c2j-9gv5-cj73, GHSA-7f5h-v6xp-fcq8, GHSA-wqp7-x3pw-xc5r, GHSA-x746-7m8f-x49c. Two are fixed by starlette 0.47.2/0.49.1; full remediation requires **1.3.1**. **Status: FIXED** — `fastapi` 0.115.6 → 0.139.0, `starlette` pinned explicitly at 1.3.1 (new durable security floor in `pyproject.toml`), Owner-approved, decision **D-065**. `pip-audit` clean post-bump; all gates green. Root cause of late detection: pip-audit runs in CI, and the advisories postdate the 2026-06-27 run — recurring-task cadence (below) is the control that caught it here.

---

### 2026-06-27 — Gate G-5 (Security configuration) — ✅ APPROVED by Owner

| Field | Value |
|---|---|
| Gate | **G-5 — Security configuration** (§25.13, D-037) |
| Status | ✅ **Approved by Owner — 2026-06-27** |
| Scope | Sprint 11 Phase A changes touching secrets handling / isolation / rate-limit semantics: Task 11.1 (`DEPLOY_ENV` + `PROD_BOT_TOKEN_FINGERPRINT` production-fingerprint boot assertion, D-060; `core/environment.py` safety-rule registry) and Task 11.5 (the five §25.9 security categories). |
| Verified | No new leak path (scrubber + Settings repr + Sentry before_send redact secrets; fingerprint is a one-way hash, no secret stored); rate-limit/abuse semantics enforced (45 security tests green); test-vs-production isolation guard refuses to boot the sandbox against the production bot. |
| Git SHA at approval | `03c9885` (worktree `happy-bose-71ed46`, pushed to origin) |

---

### 2026-06-27 — Security Validation Run — Sprint 11 Task 11.5 (full security suite)

| Field | Value |
|---|---|
| Git SHA | this commit (Sprint 11 Task 11.5); worktree `happy-bose-71ed46` |
| Environment | local |
| Sprint | 11 |
| Triggered by | Task 11.5 — security test suite across all five §25.9 categories |
| Suites run | `tests/security/{input_validation,authorization,abuse_protection,data_protection,dependency_scan}` (+ the 11.1 isolation test) |
| pip-audit | CI gate (`.github/workflows/ci.yml`), not run locally this task |
| bandit | clean (0 findings); `tests/` excluded by `[tool.bandit].exclude_dirs` |
| Total cases | 45 | Passed | 45 | Failed | 0 |
| Notes | §25.9.1 malformed/oversized/forged input rejected at the boundary; §25.9.2 role-gating + HMAC forgery rejection; §25.9.3 message-rate/daily/cooldown/ban enforced, owner exempt, counters keyed per-user (no payload-variation bypass); §25.9.4 scrubber + Settings repr + Sentry before_send redact secrets; §25.9.5 exact dependency pins, `.env` gitignored + not committed, pip-audit/bandit wired in CI. |

**Findings raised this run (if any)**
- None.

---

### 2026-06-27 — Security Validation Run — Sprint 11 Task 11.1 (test-environment isolation)

| Field | Value |
|---|---|
| Git SHA | this commit (Sprint 11 Task 11.1); worktree `happy-bose-71ed46`, parent `066b43a` |
| Environment | local |
| Sprint | 11 |
| Triggered by | Task 11.1 — `DEPLOY_ENV` plumbing + production-fingerprint boot assertion (D-032/D-060) |
| Suites run | `tests/security/test_environment_isolation.py` (data_security category — §25.9.4) |
| pip-audit | not run this task (Dependency Security suite wiring is Task 11.5) |
| bandit | clean (0 findings) on `core/security.py`, `core/environment.py`, `core/config.py` |
| Total cases | 4 | Passed | 4 | Failed | 0 |
| Notes | First occupant of `tests/security/`. The guard refuses to boot a `DEPLOY_ENV=test` process whose `BOT_TOKEN` matches the configured `PROD_BOT_TOKEN_FINGERPRINT` (SHA-256, one-way — no secret stored, Hard Rule 6). The check is generic/extensible: `core/environment.py::ENVIRONMENT_SAFETY_RULES` (future rules: test must not use a production DB/Redis/storage/webhook). |

**Findings raised this run (if any)**
- None.

**Gate:** This task changes security/isolation configuration → Gate **G-5** (Security configuration). Awaiting Owner `Gate G-5 approved`.

---

### Pre-Sprint 0 — 2026-06-23

| Field | Value |
|---|---|
| State | No security suite exists. No dependencies installed. No application code. |
| Open findings | 0 |
| Notes | This file is initialized empty. The first real entry will be a `pip-audit` clean run at the end of Sprint 0 (after dependencies are pinned). The full security suite arrives in Sprint 11. |

---

## Recurring Tasks

| Task | Cadence | Owner | Last Run |
|---|---|---|---|
| `pip-audit` scan | Every PR + nightly | CI | — |
| `bandit` scan | Every PR | CI | — |
| yt-dlp version review | Monthly | (assigned in Sprint 5) | — |
| Secrets rotation: `BOT_TOKEN` | Yearly / on compromise | Owner | — |
| Secrets rotation: `DB_PASSWORD` | Every 90 days | Owner | — |
| Secrets rotation: Redis AUTH | Every 90 days | Owner | — |
| Secrets rotation: `BOT_WEBHOOK_SECRET` | Every 90 days | Owner | — |
| Full security-suite run | Every release | CI | — |
| External penetration test | Before V2 launch | external | — |

---

## Release Snapshots

```
### Release V<X.Y> — <Date>

| Field | Value |
|---|---|
| Git tag | v<X.Y>.<Z> |
| Categories run | input_validation, authorization, abuse_protection, data_security, dependency_security |
| Open Critical / High at release | <N> / <N> (must be 0 / 0 for V1 launch) |
| Open Medium at release | <N> |
| Open Low at release | <N> |
| Dependency advisories outstanding | <list> |
| Sign-off (Owner) | Gate G-5 approved on <date> |
```

---

> **End of `SECURITY_REPORT.md`.** Append-only. Update on every security-relevant change.
