#!/bin/sh
# yt-dlp wrapper (installed as /usr/local/bin/yt-dlp; real binary is yt-dlp.real).
#
# PERSISTENT COOKIE JAR. YouTube rotates the session cookies (__Secure-*PSIDTS,
# SIDCC, …) on nearly every request and expects the client to keep the new values.
# The previous version of this wrapper handed each run a private copy and deleted
# it afterwards, so those rotated values were discarded every single time — the
# account session could never persist its own rotation and died within minutes of
# each fresh export. This version writes refreshed cookies back to the master.
#
# Concurrency model (multiple workers run yt-dlp simultaneously):
#   * The master is bind-mounted from the host, so it CANNOT be replaced by rename
#     (a mount point is busy) — it must be rewritten in place, which is not atomic.
#     A reader could therefore observe a half-written file; flock is what prevents it.
#   * SHARED lock (brief) while copying master -> private jar.
#   * NO lock while yt-dlp runs — downloads take minutes and must not serialize.
#   * EXCLUSIVE lock (brief) for the write-back.
#   * Optimistic concurrency: we remember the master's checksum at copy time and
#     skip the write-back if another run has already refreshed it meanwhile, so a
#     long-running job can never clobber newer cookies with its own stale ones.
#
# The write-back is gated on the jar being VALID, not on yt-dlp's exit code: cookies
# rotate during any successful exchange with Google, including runs that ultimately
# fail (e.g. a per-video bot-check wall). Gating on the exit code would discard
# exactly the refreshed cookies we are trying to keep whenever extraction is blocked.
#
# Degrades safely: no master file, no mktemp, no flock, or an unwritable master ->
# fall back to a plain run / skip the write-back. yt-dlp is never blocked.

MASTER=/etc/yt-dlp/cookies.txt
LOCK=/tmp/ytdlp-cookies.lock
REAL=/usr/local/bin/yt-dlp.real
MIN_COOKIE_LINES=5

# No cookies configured -> nothing to manage.
[ -s "$MASTER" ] || exec "$REAL" "$@"

JAR=$(mktemp /tmp/ytc.XXXXXX) || exec "$REAL" "$@"
trap 'rm -f "$JAR"' EXIT INT TERM

HAVE_LOCK=0
if command -v flock >/dev/null 2>&1 && exec 9>>"$LOCK" 2>/dev/null; then
    HAVE_LOCK=1
fi

# Cheap content signature (POSIX; the jar is a few KB).
sig() { cksum < "$1" 2>/dev/null || echo unknown; }

# A jar worth persisting: Netscape header + a plausible number of cookie lines.
# Guards against persisting a truncated/empty jar from a killed run.
jar_is_valid() {
    [ -s "$1" ] || return 1
    head -n 1 "$1" | grep -q 'Netscape HTTP Cookie File' || return 1
    [ "$(awk 'NF && $0 !~ /^#/' "$1" | wc -l)" -ge "$MIN_COOKIE_LINES" ] || return 1
}

# --- snapshot the master (shared lock) ---
[ "$HAVE_LOCK" = 1 ] && flock -s 9
if ! cp "$MASTER" "$JAR" 2>/dev/null; then
    [ "$HAVE_LOCK" = 1 ] && flock -u 9
    exec "$REAL" "$@"
fi
SIG_AT_COPY=$(sig "$MASTER")
[ "$HAVE_LOCK" = 1 ] && flock -u 9

# --- the actual run (no lock held) ---
"$REAL" --cookies "$JAR" "$@"
rc=$?

# --- persist refreshed cookies (exclusive lock, in-place rewrite) ---
if jar_is_valid "$JAR" && ! cmp -s "$JAR" "$MASTER"; then
    [ "$HAVE_LOCK" = 1 ] && flock -x 9
    if [ "$(sig "$MASTER")" = "$SIG_AT_COPY" ]; then
        # In-place: a bind-mounted file cannot be renamed over. Held under the
        # exclusive lock, so no reader can observe the partial write.
        cat "$JAR" > "$MASTER" 2>/dev/null || true
    fi
    [ "$HAVE_LOCK" = 1 ] && flock -u 9
fi

exit $rc
