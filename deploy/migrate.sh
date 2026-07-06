#!/usr/bin/env sh
# Apply database migrations to head — MASTER_PLAN Sprint 12.
#
# Migrations MUST reach the current head BEFORE the app boots (deploy/README.md §3):
# the bot/worker/api processes assume the schema is current and do NOT self-migrate.
#
# On Railway, set this as the service **pre-deploy command** (Settings → Deploy →
# Pre-Deploy Command) on ONE service (e.g. the api), so it runs once per release
# with the app's DB_* env in scope, before the new containers start. Locally:
#
#   sh deploy/migrate.sh
#
# Requires the app environment (DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD) to be
# set — alembic/env.py builds the connection from core.config.Settings.

set -eu

echo "==> alembic upgrade head"
alembic upgrade head

echo "==> current head:"
alembic current

echo "Migrations applied."
