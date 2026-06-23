# Telegram SaaS Download Bot

A production-grade Telegram download platform (V1) built to scale from hundreds to
tens of thousands of daily users, with a queue, a global `file_id` cache, per-user
history, an in-bot admin panel, statistics, broadcasts, error tracking, and a
provider-abstracted download engine.

> **Single source of truth:** [`MASTER_PLAN.md`](MASTER_PLAN.md).
> Read **Section 1 (AI Agent Execution Rules)** before touching anything.
> Implementation status lives in [`PROJECT_PROGRESS.md`](PROJECT_PROGRESS.md).

## Canonical documents

| Document | Purpose |
|---|---|
| [`MASTER_PLAN.md`](MASTER_PLAN.md) | Architecture, locked schema, sprint plan, decision log. **Authoritative.** |
| [`PROJECT_PROGRESS.md`](PROJECT_PROGRESS.md) | Live implementation status; updated every task. |
| [`TEST_RESULTS.md`](TEST_RESULTS.md) | Append-only test-run outcomes. |
| [`SECURITY_REPORT.md`](SECURITY_REPORT.md) | Append-only security findings. |
| [`PERFORMANCE_REPORT.md`](PERFORMANCE_REPORT.md) | Append-only load/stress results. |

`project_reference.md` and `database_reference.md` are **superseded** and retained
for history only.

## Architecture at a glance

Strict inward dependency direction (MASTER_PLAN Section 8), enforced by `import-linter`:

```
bot/ · api/ · workers/   →   services/   →   domain/   →   core/
                              infrastructure/  →  domain/ · core/
```

- `bot/`, `api/`, `workers/` import infrastructure **only** at their composition root.
- `services/` depend on `domain/protocols/`, never on `infrastructure/`.
- Telegram, yt-dlp, FFmpeg, Postgres, Redis are vendors behind adapters in `infrastructure/`.

## Tech stack

Python 3.13 · Aiogram 3 · FastAPI · PostgreSQL 15 · SQLAlchemy 2 (async) · Alembic ·
Redis 7 · PgBouncer · yt-dlp · FFmpeg · structlog · Sentry. Full pins in
[`MASTER_PLAN.md` Section 6](MASTER_PLAN.md).

## Local development

Requires Python 3.13, Docker, and Docker Compose.

```bash
# 1. Python toolchain
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pre-commit install

# 2. Environment
cp .env.example .env                 # then fill in real values

# 3. Local infrastructure (postgres, redis, pgbouncer, uptime-kuma)
docker compose -f deploy/docker-compose.yml up -d
```

## Quality gates

```bash
ruff check .            # lint
ruff format --check .   # format
mypy --config-file=mypy.ini .   # strict type-check
lint-imports            # architecture dependency rules
pytest                  # tests
pip-audit               # dependency vulnerability scan
bandit -r . -c pyproject.toml   # static security scan
```

CI runs all of the above on every push and pull request to `main`
(`.github/workflows/ci.yml`).

## Repository layout

See [`MASTER_PLAN.md` Section 7](MASTER_PLAN.md). Top-level package directories are
**locked**; new top-level directories require Owner approval.

## Contributing

Every change follows the Definition of Done in
[`MASTER_PLAN.md` Section 1.8](MASTER_PLAN.md) and updates
[`PROJECT_PROGRESS.md`](PROJECT_PROGRESS.md) in the same change set. Work proceeds
one sprint at a time; the agent stops at each sprint's stop point for Owner approval.
