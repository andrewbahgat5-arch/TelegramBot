# Release Checklist — V1 Production Deploy

> MASTER_PLAN Sprint 12 (Launch Readiness). The single ordered procedure for
> cutting a production release: pre-flight gates → build/tag → migrate → deploy →
> smoke → sign-off. Companion docs: [`README.md`](README.md) (runbook),
> [`SMOKE_TEST.md`](SMOKE_TEST.md), [`restore-drill-report.md`](restore-drill-report.md).
>
> **Binding rules:** never deploy to production without explicit Owner
> authorization (D-032). Migrations are additive and never rewritten once merged
> (Hard Rule 8). Cut releases from tagged images so rollback = redeploy a prior tag.

Copy this checklist into the release ticket / PR and tick as you go.

---

## Phase 0 — Pre-flight (on the release commit, no infra needed)

- [ ] Branch is the intended release commit; working tree clean (`git status`).
- [ ] **Quality gates green** (the same set CI enforces, MASTER_PLAN §25.13):
  - [ ] `ruff check .` and `ruff format --check .`
  - [ ] `mypy --config-file=mypy.ini .` (strict, 0 errors)
  - [ ] `lint-imports` (architecture layers, all contracts kept)
  - [ ] `pytest` (unit + integration; note any environment-skipped suites)
  - [ ] `pytest tests/security` (security suite) + `bandit -r . -c pyproject.toml` (0)
  - [ ] `pip-audit` (0 known CVEs, or documented + Owner-approved — see D-065)
- [ ] **Human Verification Gates** cleared for everything in the release
      (D-037): all `[~]` sprints in `PROJECT_PROGRESS.md` are Owner-signed-off.
- [ ] `alembic heads` shows a **single** head; note it: `__________________`.
- [ ] `CHANGELOG` / release notes drafted (what changed, migration id, config deltas).

## Phase 1 — Configuration

- [ ] `.env.production` exists on the target host, filled from
      [`.env.production.example`](../.env.production.example); secrets injected
      from the secret backend, **not** committed.
- [ ] Compose infra secrets available (`DB_NAME`/`DB_USER`/`DB_PASSWORD` via shell
      env or `deploy/.env`) so `${VAR:?}` guards pass.
- [ ] `DEPLOY_ENV=production`; `SENTRY_ENVIRONMENT=production`; `LOG_FORMAT=json`.
- [ ] Open questions that gate launch resolved: **OQ-1** (Sentry), **OQ-3** (host),
      **OQ-5** (alerts chat) — or explicitly waived by the Owner for this release.

## Phase 2 — Build & tag

- [ ] Choose an immutable `IMAGE_TAG` (e.g. the short git SHA): `__________`.
- [ ] Build the three app images:
      `IMAGE_TAG=<tag> docker compose -f deploy/docker-compose.prod.yml build`
- [ ] (If using a registry) push `bot`/`worker`/`api` at `<tag>`.
- [ ] Record the **previous** good tag for rollback: `__________`.

## Phase 3 — Migrate (before app boot)

- [ ] Bring up infra only:
      `docker compose -f deploy/docker-compose.prod.yml up -d postgres redis pgbouncer`
- [ ] Take/confirm a fresh backup exists **before** migrating (§14.8; rollback safety).
- [ ] `alembic upgrade head`; then `alembic current` == the head noted in Phase 0.

## Phase 4 — Deploy

- [ ] Start the app tier:
      `IMAGE_TAG=<tag> docker compose -f deploy/docker-compose.prod.yml up -d`
- [ ] `docker compose -f deploy/docker-compose.prod.yml ps` — all services healthy.
- [ ] Point Uptime Kuma monitors at `/v1/health` and `/v1/ready`.

## Phase 5 — Smoke test (Task 12.3)

- [ ] `deploy/smoke-test.sh https://<api-host>:<port>` → **PASSED (3/3)**.
- [ ] Manual bot-flow checklist in [`SMOKE_TEST.md`](SMOKE_TEST.md) §2 complete.
- [ ] Forced-alert test: emit a `CRITICAL` from each process; confirm one throttled
      Telegram alert arrives and Sentry tags `component` correctly (README §6).
- [ ] Re-run E2E scenarios **S-1** and **S-2** against production (Task 12.4).

## Phase 6 — Record & sign off (Task 12.7)

- [ ] Append a release entry to **`TEST_RESULTS.md`** (smoke + E2E results, date, tag).
- [ ] Append a release entry to **`SECURITY_REPORT.md`** (pre-release scan results).
- [ ] Append a release entry to **`PERFORMANCE_REPORT.md`** (baseline / load notes).
- [ ] Update `PROJECT_PROGRESS.md`: mark Sprint 12 tasks, add a Session Handoff row,
      flip the state counters; **mark V1 complete**.
- [ ] Schedule the two recurring drills (Task 12.6): first **restore drill** at
      T+30 days, first **L4 production-shadow load run** at T+90 days.
- [ ] **Gate G-8** (§25): Owner signs off on smoke + E2E + the three report entries.

**Release sign-off:** tag `__________`, date `__________`, Owner `__________`,
result **GO / NO-GO**.

---

## Rollback (if any phase fails)

Follow [`README.md`](README.md) §4:
1. **App regression** → redeploy the previous `IMAGE_TAG` (stateless; no DB change).
2. **Migration regression** → `alembic downgrade -1` + redeploy the matching tag,
   or restore from backup (§5) if a downgrade would lose data.
3. Confirm `/v1/ready` = 200 and Uptime Kuma green before declaring recovery, then
   re-run `smoke-test.sh`.
