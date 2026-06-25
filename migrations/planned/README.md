# `migrations/planned/` — non-wired migration skeletons

Files here are **planning artifacts, not live migrations.**

- Alembic's `script_location = migrations` scans **`migrations/versions/` only** (no
  `version_locations` override), so nothing in this directory is discovered by
  `alembic upgrade`/`downgrade`/`revision`. The current head is unchanged
  (`202606230002`).
- These files are excluded from `ruff` (`pyproject.toml` → `extend-exclude`) and
  `mypy` (`mypy.ini` → `exclude`), and `bandit` already skips `migrations/`.
- They are **not** Python packages (no `__init__.py`) and are not imported anywhere.

## Promoting a skeleton to a real migration

When the owning sprint is approved and implementation begins:

1. Copy the skeleton to `migrations/versions/{YYYYMMDDHHMM}_{slug}.py` (Section 19.2 naming).
2. Set `down_revision` to the **then-current head** (`alembic heads`) — it will likely
   be a Sprint-10+ revision, not `202606230002`.
3. Assign a real `revision` id and finish the `upgrade()`/`downgrade()` bodies + backfills.
4. Follow the Section 19.4 "Adding a New Table" checklist (model, repo, protocol, tests,
   component card).

## Contents

- `ads_v2_schema.py` — **Only the deferred `ad_events` analytics table (task 9.5.9).**
  The Ads v2 core schema was promoted to `migrations/versions/202606240001_ads_v2_schema.py`
  on 2026-06-25 and applied. See MASTER_PLAN §23 "Sprint 9.5 — Ads v2", D-042–D-045,
  §13.6, §19.3.
