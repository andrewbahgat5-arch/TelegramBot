"""Truth table for the cookie health classifier (DESIGN_COOKIE_POOL.md §7).

The central guarantee under test: **route failures never reduce cookie health.** These
tests are the executable form of that rule — if someone later folds a wall or a proxy
error into the auth allowlist, the pool would burn itself down and these fail first.
"""

from __future__ import annotations

import pytest

from domain.entities.cookie import CookieImpact
from services.cookie_classifier import classify


def test_clean_exit_is_success() -> None:
    assert classify(0, "").impact is CookieImpact.SUCCESS


def test_clean_exit_is_success_even_with_warnings() -> None:
    # A walled run exits non-zero, so rc=0 means the session did its job.
    verdict = classify(0, "WARNING: No title found in player responses")
    assert verdict.impact is CookieImpact.SUCCESS


@pytest.mark.parametrize(
    "stderr",
    [
        "WARNING: [youtube] The provided YouTube account cookies are no longer valid.",
        "ERROR: account cookies for this session are no longer valid, they have been rotated",
        "WARNING: cookies have been rotated by the browser",
    ],
)
def test_rotated_session_is_expired_immediately(stderr: str) -> None:
    # Terminal: retrying cannot help, so this skips cooldown entirely.
    verdict = classify(1, stderr)
    assert verdict.impact is CookieImpact.EXPIRED
    assert verdict.affects_health is True
    assert verdict.reason


@pytest.mark.parametrize(
    "stderr",
    [
        "ERROR: could not parse cookie file",
        "ERROR: cookie file is malformed",
        "ERROR: This account has been terminated",
        "ERROR: this account has been suspended",
    ],
)
def test_unusable_file_or_dead_account_is_invalid(stderr: str) -> None:
    verdict = classify(1, stderr)
    assert verdict.impact is CookieImpact.INVALID
    assert verdict.affects_health is True


@pytest.mark.parametrize(
    "stderr",
    [
        "ERROR: Please sign in to view this content",
        "ERROR: Login required",
        "ERROR: authentication failed",
        "ERROR: HTTP Error 401: Unauthorized",
    ],
)
def test_session_rejection_is_a_strike(stderr: str) -> None:
    verdict = classify(1, stderr)
    assert verdict.impact is CookieImpact.AUTH_FAILURE
    assert verdict.affects_health is True


# --- The guarantee: none of these may ever touch cookie health ---------------------


@pytest.mark.parametrize(
    ("label", "stderr"),
    [
        # THE case. Measured 2026-07-18: this wall tracks the egress route, not the
        # cookie — identical with and without cookies on the proxy, absent over WARP.
        ("bot-check wall", "ERROR: Sign in to confirm you're not a bot. Use --cookies"),
        ("bot-check wall, curly apostrophe",
         "ERROR: Sign in to confirm you’re not a bot."),  # noqa: RUF001 - real yt-dlp text
        ("proxy failure", "ERROR: Unable to connect to proxy"),
        ("socks failure", "ERROR: SOCKS5 proxy server sent invalid data"),
        ("tunnel failure", "ERROR: Tunnel connection failed: 407 Proxy Authentication"),
        ("connection reset", "ERROR: Connection reset by peer"),
        ("timeout", "ERROR: The read operation timed out"),
        ("dns", "ERROR: Temporary failure in name resolution"),
        ("http 503", "ERROR: HTTP Error 503: Service Unavailable"),
        ("rate limit", "ERROR: HTTP Error 429: Too Many Requests"),
        ("private video", "ERROR: Private video. Sign in if you've been granted access"),
        ("removed", "ERROR: This video has been removed by the uploader"),
        ("geo", "ERROR: The uploader has not made this video available in your country"),
        ("members only", "ERROR: Join this channel to get access to members-only content"),
        ("no video in tweet", "ERROR: No video could be found in this tweet"),
        ("unrecognised", "ERROR: something nobody has seen before"),
    ],
)
def test_route_and_content_failures_never_affect_cookie_health(
    label: str, stderr: str
) -> None:
    verdict = classify(1, stderr)
    assert verdict.impact is CookieImpact.NONE, f"{label} must not blame the cookie"
    assert verdict.affects_health is False, f"{label} must not blame the cookie"


def test_wall_text_containing_sign_in_is_not_read_as_auth() -> None:
    """Regression guard for the subtlest failure mode: the bot-check wall literally
    says "Sign in to confirm you're not a bot". Matching the auth allowlist on those
    words would strike a cookie for a route problem — the exact bug this design exists
    to prevent."""
    verdict = classify(1, "ERROR: Sign in to confirm you're not a bot. Use --cookies")
    assert verdict.impact is CookieImpact.NONE


def test_private_video_sign_in_text_is_content_not_auth() -> None:
    # "Private video. Sign in if you've been granted access" — a cookie swap won't help.
    assert classify(1, "ERROR: Private video. Sign in if you've").impact is CookieImpact.NONE


def test_empty_stderr_on_failure_is_not_the_cookies_fault() -> None:
    assert classify(1, "").impact is CookieImpact.NONE


def test_expired_wins_over_a_co_occurring_auth_line() -> None:
    # Terminal verdicts are checked first so they are never downgraded to a strike.
    stderr = "ERROR: Please sign in\nWARNING: The provided cookies are no longer valid"
    assert classify(1, stderr).impact is CookieImpact.EXPIRED
