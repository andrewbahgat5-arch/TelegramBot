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
# The write-back MERGES rather than replaces. A straight copy of yt-dlp's jar over the
# master was measured to silently destroy the export: after one run the master had lost
# SID, HSID, SSID, APISID, SAPISID, LOGIN_INFO and the whole __Secure-1P* set, because a
# jar only ever contains what that run's requests happened to keep. Merging means a
# rotated value always wins, a brand-new cookie is added, and a cookie the run did not
# touch is preserved — so the account export can never be eroded by a single bad
# exchange. Cookies are keyed on (domain, path, name), with the #HttpOnly_ prefix
# normalised away so an HttpOnly variant updates its plain counterpart.
#
# Degrades safely: no master file, no mktemp, no flock, or an unwritable master ->
# fall back to a plain run / skip the write-back. yt-dlp is never blocked.

# WHICH cookie file to use is decided in Python (the cookie pool picks one and exports
# YTDLP_COOKIE_FILE); HOW to use it safely is decided here. Falling back to the single
# master keeps every pre-pool deployment working unchanged.
MASTER="${YTDLP_COOKIE_FILE:-/etc/yt-dlp/cookies.txt}"
REAL=/usr/local/bin/yt-dlp.real
MIN_COOKIE_LINES=5

# One lock per cookie file, so two different cookies never serialise against each other.
LOCK="/tmp/ytdlp-cookies.$(printf %s "$MASTER" | tr -c 'A-Za-z0-9' '_').lock"

# No cookies configured -> nothing to manage.
[ -s "$MASTER" ] || exec "$REAL" "$@"

JAR=$(mktemp /tmp/ytc.XXXXXX) || exec "$REAL" "$@"
trap 'rm -f "$JAR" "${JAR}.merged"' EXIT INT TERM

HAVE_LOCK=0
if command -v flock >/dev/null 2>&1 && exec 9>>"$LOCK" 2>/dev/null; then
    HAVE_LOCK=1
fi

# Cheap content signature (POSIX; the jar is a few KB).
sig() { cksum < "$1" 2>/dev/null || echo unknown; }

# Count real cookie lines. "#HttpOnly_..." IS a cookie line, not a comment.
cookie_lines() {
    awk 'NF && ($0 !~ /^#/ || $0 ~ /^#HttpOnly_/)' "$1" | wc -l
}

# A jar worth persisting: Netscape header + a plausible number of cookie lines.
# Guards against persisting a truncated/empty jar from a killed run.
jar_is_valid() {
    [ -s "$1" ] || return 1
    head -n 1 "$1" | grep -q 'Netscape HTTP Cookie File' || return 1
    [ "$(cookie_lines "$1")" -ge "$MIN_COOKIE_LINES" ] || return 1
}

# Merge yt-dlp's jar ($1) into the master ($2) -> stdout. Master order and comments are
# preserved; a cookie present in both takes the jar's (refreshed) value; jar-only cookies
# are appended; master-only cookies are kept untouched.
merge_jar_into_master() {
    awk -F'\t' '
        function is_cookie(line) { return (NF >= 7) && (line !~ /^#/ || line ~ /^#HttpOnly_/) }
        function key(d, p, n) { sub(/^#HttpOnly_/, "", d); return d SUBSEP p SUBSEP n }
        FNR == NR {                      # pass 1: the jar
            if (is_cookie($0)) jar[key($1, $3, $6)] = $0
            next
        }
        {                                # pass 2: the master
            if (!is_cookie($0)) { print; next }
            k = key($1, $3, $6)
            if (k in jar) { print jar[k]; used[k] = 1 } else print
        }
        END { for (k in jar) if (!(k in used)) print jar[k] }
    ' "$1" "$2"
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
        MERGED="${JAR}.merged"
        if merge_jar_into_master "$JAR" "$MASTER" > "$MERGED" 2>/dev/null \
            && jar_is_valid "$MERGED" \
            && [ "$(cookie_lines "$MERGED")" -ge "$(cookie_lines "$MASTER")" ]; then
            # In-place: a bind-mounted file cannot be renamed over. Held under the
            # exclusive lock, so no reader can observe the partial write. The
            # never-shrink check is a last guard against a merge bug silently
            # dropping cookies.
            cat "$MERGED" > "$MASTER" 2>/dev/null || true
        fi
        rm -f "$MERGED"
    fi
    [ "$HAVE_LOCK" = 1 ] && flock -u 9
fi

exit $rc
