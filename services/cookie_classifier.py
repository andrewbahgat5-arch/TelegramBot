"""Classify a yt-dlp outcome into a cookie health verdict (DESIGN_COOKIE_POOL.md §7).

Pure and framework-free: ``(returncode, stderr) -> CookieVerdict``. No I/O, no state.

**The rule that governs this module:** only authentication/session signals may reduce a
cookie's health. Everything else — bot-check walls, proxy or WARP failures, timeouts,
HTTP 5xx, content errors, anything unrecognised — returns :attr:`CookieImpact.NONE`.

This is not a stylistic preference. It was measured on 2026-07-18: YouTube's "confirm
you're not a bot" wall tracked the *egress route*, not the cookie — identical results with
and without cookies on the residential proxy (both walled) while WARP passed both ways. A
classifier that blamed the cookie would strike one, rotate, hit the same wall, strike the
next, and burn an entire healthy pool in minutes over a problem no cookie can fix.

So the structure here is an **allowlist**: a signal must be explicitly recognised as an
auth/session problem to count. The default is "not the cookie's fault". A false strike
removes capacity from a healthy pool; a missed signal only delays detection by one more
consecutive failure. The asymmetry favours doing nothing.
"""

from __future__ import annotations

import re

from domain.entities.cookie import CookieImpact, CookieVerdict

# --- Signals that DO affect cookie health (the entire allowlist) --------------------

# Google rotated the session out from under us; the export is dead. Retrying cannot help,
# so this skips cooldown and goes straight to EXPIRED.
_EXPIRED_PATTERNS = (
    re.compile(r"cookies are no longer valid", re.I),
    re.compile(r"account cookies.{0,40}no longer valid", re.I),
    re.compile(r"cookies.{0,20}(have|has) been rotated", re.I),
)

# The file itself is unusable, or the account is gone. A human must replace it.
_INVALID_PATTERNS = (
    re.compile(r"could not (parse|read) cookie", re.I),
    re.compile(r"cookie file.{0,30}(malformed|invalid|not.{0,10}valid)", re.I),
    re.compile(r"'?cookies'? file is not.{0,20}netscape", re.I),
    re.compile(r"account has been terminated", re.I),
    re.compile(r"this account has been (closed|suspended|disabled)", re.I),
)

# The session was rejected for this request: a strike, subject to threshold + cooldown.
_AUTH_FAILURE_PATTERNS = (
    re.compile(r"please sign in", re.I),
    re.compile(r"sign in to your account", re.I),
    re.compile(r"login required", re.I),
    re.compile(r"authentication (failed|required)", re.I),
    re.compile(r"unable to log ?in", re.I),
    re.compile(r"http error 401", re.I),
)

# --- Signals explicitly recognised as NOT the cookie's fault ------------------------
# These exist only to be documented, logged and unit-tested. They all resolve to NONE,
# which is also the default — but naming them stops a future edit from "helpfully"
# folding a route failure into the auth list.

_ROUTE_PATTERNS = (
    re.compile(r"confirm you.{0,3}re not a bot", re.I),  # the wall — tracks the ROUTE
    re.compile(r"proxy", re.I),
    re.compile(r"socks", re.I),
    re.compile(r"tunnel connection failed", re.I),
    re.compile(r"connection (reset|refused|aborted|timed out)", re.I),
    re.compile(r"read timed out|timeout", re.I),
    re.compile(r"temporary failure in name resolution|getaddrinfo", re.I),
    re.compile(r"http error 5\d\d", re.I),
    re.compile(r"http error 429", re.I),  # rate limit: the IP is hot, not the session
)

_CONTENT_PATTERNS = (
    re.compile(r"video unavailable", re.I),
    re.compile(r"private video", re.I),
    re.compile(r"has been removed", re.I),
    re.compile(r"not available in your country|geo", re.I),
    re.compile(r"members[- ]only", re.I),
    re.compile(r"age[- ]restricted", re.I),  # arguably auth, but a cookie swap won't fix it
    re.compile(r"no video could be found", re.I),
)


def classify(returncode: int, stderr: str) -> CookieVerdict:
    """Map one yt-dlp run onto its effect on the cookie that was used.

    ``returncode == 0`` is success even if stderr carried warnings — a walled extraction
    exits non-zero, so a clean exit means the session did its job.
    """
    text = stderr or ""

    if returncode == 0:
        # A clean exit still carries a route signal when ``--ignore-no-formats-error`` is
        # in play: yt-dlp exits 0 with the bot-check wall in stderr and no formats. The
        # session was not rejected, but it did not prove itself either — stay neutral
        # rather than crediting a success that never happened.
        if _matches(text, _ROUTE_PATTERNS):
            return CookieVerdict(CookieImpact.NONE, "route/network failure")
        return CookieVerdict(CookieImpact.SUCCESS)

    # Order matters: the terminal verdicts are checked before the recoverable one, so
    # "cookies are no longer valid" is never downgraded to a mere strike.
    if _matches(text, _EXPIRED_PATTERNS):
        return CookieVerdict(CookieImpact.EXPIRED, _first_match(text, _EXPIRED_PATTERNS))
    if _matches(text, _INVALID_PATTERNS):
        return CookieVerdict(CookieImpact.INVALID, _first_match(text, _INVALID_PATTERNS))

    # A route or content failure short-circuits BEFORE the auth patterns. Some wall text
    # also contains the words "sign in" ("Sign in to confirm you're not a bot"), and that
    # must never be read as an authentication problem.
    if _matches(text, _ROUTE_PATTERNS):
        return CookieVerdict(CookieImpact.NONE, "route/network failure")
    if _matches(text, _CONTENT_PATTERNS):
        return CookieVerdict(CookieImpact.NONE, "content unavailable")

    if _matches(text, _AUTH_FAILURE_PATTERNS):
        return CookieVerdict(
            CookieImpact.AUTH_FAILURE, _first_match(text, _AUTH_FAILURE_PATTERNS)
        )

    # Unrecognised: recorded for statistics, never held against the cookie.
    return CookieVerdict(CookieImpact.NONE, "unclassified failure")


def _matches(text: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(p.search(text) for p in patterns)


def _first_match(text: str, patterns: tuple[re.Pattern[str], ...]) -> str:
    """The matching stderr line, trimmed — this is what reaches the admin notification."""
    for pattern in patterns:
        found = pattern.search(text)
        if not found:
            continue
        for line in text.splitlines():
            if pattern.search(line):
                cleaned = line.strip()
                for prefix in ("ERROR:", "WARNING:"):
                    if cleaned.upper().startswith(prefix):
                        cleaned = cleaned[len(prefix) :].strip()
                return cleaned[:200]
        return found.group(0)[:200]
    return ""
