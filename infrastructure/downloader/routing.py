"""Per-platform network egress policy.

Decides which upstream a request uses so the paid proxy / WARP are spent only where
they're needed:

* ``DIRECT`` — the server's own IP (no proxy). Fast and free.
* ``WARP``   — Cloudflare WARP: a clean but bandwidth-capped IP (SOCKS).
* ``PROXY``  — a residential/ISP HTTP proxy: clean *and* fast (works with aria2c).

Only platforms that actively block or rate-limit our datacenter IP are routed through a
protected egress; everything else goes DIRECT.

Verified 2026-07-16 from the production datacenter IP (direct vs. proxied extraction):

    youtube    direct → BOT-BLOCKED,  proxy → OK      ⇒ needs protection
    tiktok     direct → OK                            ⇒ direct
    facebook   direct → OK                            ⇒ direct
    instagram  direct → needs login (cookies); a proxy does NOT change that ⇒ direct
    twitter    not IP-blocked (content/login-gated)   ⇒ direct

The policy is deliberately tiny and pure so future rules slot in here without touching
the provider — e.g. a size-based split (WARP under 500 MB, PROXY at/over 500 MB) is a
change to :func:`plan_egress` alone, using the ``size_bytes`` it already receives.
"""

from __future__ import annotations

from enum import StrEnum


class Egress(StrEnum):
    """Where a yt-dlp request egresses from."""

    DIRECT = "direct"
    WARP = "warp"
    PROXY = "proxy"


# Platforms that block / rate-limit datacenter IPs and therefore need a clean egress.
# Add a platform here (one line) if it starts blocking us; remove one that stops.
PROTECTED_PLATFORMS: frozenset[str] = frozenset({"youtube"})


def plan_egress(
    platform: str, *, size_bytes: int | None = None, metadata_only: bool = False
) -> tuple[Egress, ...]:
    """Ordered egresses to try for ``platform`` — primary first, then fallbacks.

    ``metadata_only`` marks the extraction (metadata) step. A protected platform's
    metadata goes through the residential proxy **and nothing else** — no WARP, no
    DIRECT. Two reasons:

    * WARP exits from shared Cloudflare ranges that YouTube challenges far more often
      than a residential IP, so a WARP retry after a proxy failure mostly just burns
      seconds and returns the same block.
    * Account cookies are attached to extraction. Presenting one account's session
      from a second, different-looking IP is exactly the pattern that gets a Google
      session invalidated — so the session must stay pinned to one egress.

    Downloads keep the WARP fallback: media fetches are the expensive, resumable part
    and benefit from a second route when the proxy stalls mid-transfer.

    ``size_bytes`` (the download's expected size, or ``None`` at extraction time) is
    accepted now and currently ignored, so a future size-based split lives here only:

        if platform in PROTECTED_PLATFORMS:
            if size_bytes is not None and size_bytes < 500 * 1024 * 1024:
                return (Egress.WARP, Egress.PROXY)   # small ⇒ WARP first
            return (Egress.PROXY, Egress.WARP)       # large ⇒ proxy first
    """
    if platform in PROTECTED_PLATFORMS:
        if metadata_only:
            return (Egress.PROXY,)
        # Residential proxy first (fast + clean); WARP as the resilient fallback.
        return (Egress.PROXY, Egress.WARP)
    return (Egress.DIRECT,)
