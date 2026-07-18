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

Re-measured 2026-07-18, after the residential proxy's reputation degraded — YouTube now
serves it a per-video "confirm you're not a bot" wall (deterministic, 3/3 identical runs),
while WARP extracts and downloads those same videos cleanly:

    youtube metadata   proxy → walled on many videos, WARP → OK on all tested
    youtube media      WARP → OK (fmt 18/160/bestaudio all complete)

Hence the current split: **metadata always goes over WARP**, and downloads choose by size
— WARP for anything at or under :data:`WARP_MAX_DOWNLOAD_BYTES`, the residential proxy
above it (WARP is bandwidth-capped, the proxy is fast and works with aria2c's 16 parallel
connections). The policy stays tiny and pure so thresholds are a one-line change here.
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

# Download size split for protected platforms: at or under this, prefer WARP; above it,
# prefer the residential proxy. The default is overridable per deployment via the
# ``YTDLP_WARP_MAX_DOWNLOAD_MB`` env var (core.config → YtdlpProvider → plan_egress), so
# retuning the threshold needs no code change.
WARP_MAX_DOWNLOAD_BYTES = 500 * 1024 * 1024  # 500 MB


def plan_egress(
    platform: str,
    *,
    size_bytes: int | None = None,
    metadata_only: bool = False,
    warp_max_bytes: int = WARP_MAX_DOWNLOAD_BYTES,
) -> tuple[Egress, ...]:
    """Ordered egresses to try for ``platform`` — primary first, then fallbacks.

    Unprotected platforms always go DIRECT. For a protected platform:

    * ``metadata_only`` (the extraction step) → **WARP only**. WARP is currently the
      only egress that reliably gets past YouTube's per-video bot-check wall, and
      metadata is cheap, so there is nothing to gain from a slower second attempt
      over an egress that is known to be walled.
    * a download at or under ``warp_max_bytes`` → WARP first, proxy as fallback.
    * a larger download → the residential proxy first (WARP is bandwidth-capped and
      cannot use aria2c's 16 parallel connections), WARP as fallback.

    An unknown size (``None``) is treated as small: most downloads are, and WARP is
    the more reliable route. Each branch keeps the other egress as a fallback so a
    single failing upstream never takes downloads down entirely.
    """
    if platform not in PROTECTED_PLATFORMS:
        return (Egress.DIRECT,)
    if metadata_only:
        return (Egress.WARP,)
    if size_bytes is not None and size_bytes > warp_max_bytes:
        return (Egress.PROXY, Egress.WARP)
    return (Egress.WARP, Egress.PROXY)
