#!/usr/bin/env sh
# Resource sampler for the large-download stress test.
# Companion to deploy/LARGE_DOWNLOAD_STRESS_TEST.md.
#
# This OBSERVES a real run — it generates NO synthetic load (per the brief: no
# synthetic benchmarks). While you drive real downloads through the bot, this
# samples, every INTERVAL seconds, the api's live metrics (queue depth, active
# workers, DB pool in use, Redis connected) plus host memory, the temp-dir
# filesystem usage, and the temp-dir size/file-count — appending one CSV row per
# sample so you can chart RAM/disk/queue over the test window.
#
# Usage:
#   deploy/monitor-resources.sh [API_BASE_URL] [TEMP_DIR] [INTERVAL] [OUT_CSV]
# Defaults:
#   API_BASE_URL = http://localhost:8080
#   TEMP_DIR     = ${DOWNLOAD_TEMP_DIR:-/tmp/downloads}
#   INTERVAL     = 5   (seconds between samples)
#   OUT_CSV      = stress-metrics.csv
# Env:
#   MAX_SAMPLES  = 0   (0 = run until Ctrl-C; N = stop after N samples)
#
# Run it in a second terminal (or the background) for the duration of the test,
# then stop it with Ctrl-C. Linux only (Railway containers are Linux): uses
# /proc/meminfo, df, du, find — each guarded, so a missing tool blanks its column
# rather than crashing.

set -u

API_BASE_URL="${1:-http://localhost:8080}"
API_BASE_URL="${API_BASE_URL%/}"
TEMP_DIR="${2:-${DOWNLOAD_TEMP_DIR:-/tmp/downloads}}"
INTERVAL="${3:-5}"
OUT_CSV="${4:-stress-metrics.csv}"
MAX_SAMPLES="${MAX_SAMPLES:-0}"

# --- one metric value from the Prometheus exposition ------------------------
metric() { # $1 = gauge name
  printf '%s' "$METRICS" | awk -v k="$1" '$1==k {print $2; exit}'
}

mem_used_mb() {
  [ -r /proc/meminfo ] || { printf ''; return; }
  awk '/^MemTotal:/{t=$2} /^MemAvailable:/{a=$2} END{ if(t){printf "%d",(t-a)/1024} }' /proc/meminfo
}
mem_total_mb() {
  [ -r /proc/meminfo ] || { printf ''; return; }
  awk '/^MemTotal:/{printf "%d",$2/1024; exit}' /proc/meminfo
}
disk_used_pct() {
  command -v df >/dev/null 2>&1 || { printf ''; return; }
  df -P "$TEMP_DIR" 2>/dev/null | awk 'NR==2{gsub("%","",$5); print $5}'
}
tempdir_bytes() {
  { command -v du >/dev/null 2>&1 && [ -d "$TEMP_DIR" ]; } || { printf ''; return; }
  du -sb "$TEMP_DIR" 2>/dev/null | awk '{print $1}'
}
tempdir_files() {
  { command -v find >/dev/null 2>&1 && [ -d "$TEMP_DIR" ]; } || { printf ''; return; }
  find "$TEMP_DIR" -type f 2>/dev/null | wc -l | tr -d ' '
}

HEADER="timestamp_utc,queue_depth,active_workers,db_pool_in_use,redis_connected,mem_used_mb,mem_total_mb,disk_used_pct,tempdir_bytes,tempdir_files"
[ -f "$OUT_CSV" ] || printf '%s\n' "$HEADER" > "$OUT_CSV"

printf 'Sampling %s every %ss → %s (temp dir: %s). Ctrl-C to stop.\n' \
  "$API_BASE_URL" "$INTERVAL" "$OUT_CSV" "$TEMP_DIR"

n=0
while :; do
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  METRICS="$(curl -fsS --max-time 5 "$API_BASE_URL/v1/metrics" 2>/dev/null || printf '')"
  row="$ts,$(metric queue_depth),$(metric active_workers),$(metric db_pool_in_use),$(metric redis_connected),$(mem_used_mb),$(mem_total_mb),$(disk_used_pct),$(tempdir_bytes),$(tempdir_files)"
  printf '%s\n' "$row" | tee -a "$OUT_CSV"

  n=$((n + 1))
  if [ "$MAX_SAMPLES" -gt 0 ] && [ "$n" -ge "$MAX_SAMPLES" ]; then
    printf 'Reached MAX_SAMPLES=%s; stopping.\n' "$MAX_SAMPLES"
    break
  fi
  sleep "$INTERVAL"
done
