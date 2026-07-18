#!/bin/sh
# Archive container logs to disk BEFORE a deploy.
#
# Why: `docker compose up -d` recreates a container, and its json-file log goes with the
# old container. During the 2026-07-18 investigation the logs holding yt-dlp's stderr for
# a batch of Twitter/TikTok failures were destroyed by the very deploy that shipped the
# fix, so those root causes were unrecoverable. Run this first and the evidence survives.
#
# Usage:  sh deploy/capture-logs.sh [dest_dir]     (default /opt/telegram-bot/logs)
# Deploy: sh deploy/capture-logs.sh && docker compose ... up -d bot worker
#
# Keeps the last KEEP_DAYS days of archives and gzips each capture (logs compress ~10x).

set -eu

DEST="${1:-/opt/telegram-bot/logs}"
KEEP_DAYS="${KEEP_DAYS:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SERVICES="${SERVICES:-tgbot_bot tgbot_worker tgbot_api}"

mkdir -p "$DEST"

for name in $SERVICES; do
    if ! docker inspect "$name" >/dev/null 2>&1; then
        echo "skip $name (not running)"
        continue
    fi
    out="$DEST/${name}-${STAMP}.log.gz"
    # 2>&1: container logs carry both streams and we want them interleaved as emitted.
    if docker logs "$name" 2>&1 | gzip -c > "$out"; then
        echo "captured $name -> $out ($(du -h "$out" | cut -f1))"
    else
        echo "WARN: capture failed for $name" >&2
        rm -f "$out"
    fi
done

# Prune old archives so this can never fill the disk.
find "$DEST" -name '*.log.gz' -type f -mtime "+$KEEP_DAYS" -delete 2>/dev/null || true
echo "retention: kept the last $KEEP_DAYS days in $DEST"
