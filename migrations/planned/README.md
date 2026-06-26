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

_None._ All Ads v2 schema has been promoted to `migrations/versions/`:

- The Ads v2 **core** schema → `migrations/versions/202606240001_ads_v2_schema.py` (2026-06-25).
- The deferred **`ad_events`** analytics table (task 9.5.9) → `migrations/versions/202606250001_ad_events.py`
  (2026-06-25), `down_revision = 202606240001`. See MASTER_PLAN §23 "Sprint 9.5 — Ads v2",
  D-045/D-052, §19.3.
