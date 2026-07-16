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


def plan_egress(platform: str, *, size_bytes: int | None = None) -> tuple[Egress, ...]:
    """Ordered egresses to try for ``platform`` — primary first, then fallbacks.

    ``size_bytes`` (the download's expected size, or ``None`` at extraction time) is
    accepted now and currently ignored, so a future size-based split lives here only:

        if platform in PROTECTED_PLATFORMS:
            if size_bytes is not None and size_bytes < 500 * 1024 * 1024:
                return (Egress.WARP, Egress.PROXY)   # small ⇒ WARP first
            return (Egress.PROXY, Egress.WARP)       # large ⇒ proxy first
    """
    if platform in PROTECTED_PLATFORMS:
        # Residential proxy first (fast + clean); WARP as the resilient fallback.
        return (Egress.PROXY, Egress.WARP)
    return (Egress.DIRECT,)
