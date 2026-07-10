#!/bin/sh
# yt-dlp wrapper (installed as /usr/local/bin/yt-dlp; real binary is yt-dlp.real).
# Gives each invocation a PRIVATE WRITABLE COPY of the read-only master cookies so
# that:
#   * concurrent workers never corrupt/degrade the shared cookie file, and
#   * yt-dlp's end-of-run cookie save-back never crashes on the read-only master.
# The master (/etc/yt-dlp/cookies.txt) is mounted read-only and stays pristine.
MASTER=/etc/yt-dlp/cookies.txt
REAL=/usr/local/bin/yt-dlp.real
if [ -s "$MASTER" ]; then
  C=$(mktemp /tmp/ytc.XXXXXX) || exec "$REAL" "$@"
  cp "$MASTER" "$C"
  "$REAL" --cookies "$C" "$@"
  rc=$?
  rm -f "$C"
  exit $rc
fi
exec "$REAL" "$@"
