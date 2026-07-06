#!/usr/bin/env sh
# Production smoke test — MASTER_PLAN Task 12.3 (Sprint 12, Phase A/A3).
#
# The AUTOMATABLE half of the launch smoke test: the three public API endpoints
# (deploy/README.md §3). The bot-flow half (/start, downloads, /stats, ad,
# ban/unban) needs a live Telegram client and is a manual checklist —
# deploy/SMOKE_TEST.md.
#
# Usage:
#   deploy/smoke-test.sh                       # checks http://localhost:8080
#   deploy/smoke-test.sh https://api.host      # explicit base URL
#   API_BASE_URL=https://api.host deploy/smoke-test.sh
#
# Exit code 0 = all checks passed; non-zero = at least one failed (CI/gate-safe).
# Dependencies: curl (required), jq (optional — falls back to grep parsing).

set -eu

BASE_URL="${1:-${API_BASE_URL:-http://localhost:8080}}"
BASE_URL="${BASE_URL%/}" # strip a trailing slash
FAILURES=0

pass() { printf '  [PASS] %s\n' "$1"; }
fail() { printf '  [FAIL] %s\n' "$1"; FAILURES=$((FAILURES + 1)); }

printf 'Smoke test against %s\n\n' "$BASE_URL"

# --- 1. /v1/health : liveness -------------------------------------------------
printf '1. GET /v1/health (liveness)\n'
if body="$(curl -fsS --max-time 10 "$BASE_URL/v1/health" 2>/dev/null)"; then
  case "$body" in
    *'"status"'*'"ok"'*) pass "status=ok" ;;
    *) fail "unexpected body: $body" ;;
  esac
else
  fail "request failed (non-2xx or unreachable)"
fi

# --- 2. /v1/ready : readiness (200 + ready:true) ------------------------------
printf '2. GET /v1/ready (readiness: DB + Redis + queue + worker)\n'
# -w prints 000 itself on a connection failure; `|| true` just stops set -e aborting.
code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE_URL/v1/ready" 2>/dev/null || true)"
body="$(curl -s --max-time 10 "$BASE_URL/v1/ready" 2>/dev/null || true)"
if [ "$code" = "200" ]; then
  case "$body" in
    *'"ready"'*'true'*) pass "HTTP 200, ready=true" ;;
    *) fail "HTTP 200 but ready!=true: $body" ;;
  esac
else
  fail "HTTP $code (expected 200). Body: $body"
fi

# --- 3. /v1/metrics : Prometheus exposition + live gauges ---------------------
printf '3. GET /v1/metrics (Prometheus exposition)\n'
if body="$(curl -fsS --max-time 10 "$BASE_URL/v1/metrics" 2>/dev/null)"; then
  missing=""
  for gauge in queue_depth active_workers db_pool_in_use redis_connected; do
    printf '%s' "$body" | grep -q "^${gauge}" || missing="$missing $gauge"
  done
  if [ -z "$missing" ]; then
    pass "all live gauges present (queue_depth, active_workers, db_pool_in_use, redis_connected)"
  else
    fail "missing gauge(s):$missing"
  fi
else
  fail "request failed (non-2xx or unreachable)"
fi

# --- Summary ------------------------------------------------------------------
printf '\n'
if [ "$FAILURES" -eq 0 ]; then
  printf 'SMOKE TEST PASSED (3/3 endpoint checks).\n'
  printf 'Next: complete the manual bot-flow checklist in deploy/SMOKE_TEST.md.\n'
  exit 0
fi
printf 'SMOKE TEST FAILED (%s check(s) failed). See deploy/README.md §6.\n' "$FAILURES"
exit 1
