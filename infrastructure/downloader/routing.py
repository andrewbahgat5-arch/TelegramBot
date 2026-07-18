"""Per-platform network egress policy and the registry of egress endpoints.

Two separate concerns live here, deliberately:

* :func:`plan_egress` — **pure policy**: which *kind* of upstream a request should use,
  in what order. No I/O, no configuration, trivially testable.
* :class:`EgressRegistry` — **instances**: the concrete endpoints that exist in this
  deployment, each with a stable :class:`EgressId` (``"warp-1"``, ``"proxy-res-1"``).

Why the split (DESIGN_COOKIE_POOL.md §4): a cookie's session must stay pinned to one
exit IP to stay valid, so cookie affinity has to reference a *specific* endpoint, not the
abstract idea of "WARP". Adding a second WARP instance or a second proxy pool then becomes
a registry entry — no change to policy, selection, or the cookie schema.

The kinds:

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
connections).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

#: Stable identifier of one concrete egress endpoint, e.g. ``"warp-1"``. Persisted in
#: ``youtube_cookies.egress_id``, so ids must stay stable across restarts.
EgressId = str


class Egress(StrEnum):
    """The *kind* of upstream a request egresses through."""

    DIRECT = "direct"
    WARP = "warp"
    PROXY = "proxy"


#: Canonical ids for the single-instance deployment. Additional instances simply add
#: ids (``"warp-2"``, ``"proxy-res-2"``) — nothing else changes.
DIRECT_ID: EgressId = "direct"
DEFAULT_WARP_ID: EgressId = "warp-1"
DEFAULT_PROXY_ID: EgressId = "proxy-res-1"


@dataclass(frozen=True, slots=True)
class EgressEndpoint:
    """One concrete upstream. ``address`` is the yt-dlp ``--proxy`` value ("" ⇒ direct)."""

    id: EgressId
    kind: Egress
    address: str
    enabled: bool = True

    @property
    def is_configured(self) -> bool:
        """DIRECT never needs an address; every other kind is unusable without one."""
        return self.kind is Egress.DIRECT or bool(self.address)


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
    """Ordered egress *kinds* to try for ``platform`` — primary first, then fallbacks.

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


class EgressRegistry:
    """The endpoints this deployment actually has, and how a plan maps onto them.

    Today there is at most one endpoint per kind, so :meth:`plan` is a straight
    expansion of :func:`plan_egress`. When a second WARP or proxy pool is added, every
    instance of the kind is offered in registration order — the caller (and, for
    cookies, the affinity rules) picks among them.
    """

    def __init__(self, endpoints: list[EgressEndpoint]) -> None:
        self._endpoints = [e for e in endpoints if e.enabled and e.is_configured]
        self._by_id = {e.id: e for e in self._endpoints}

    @classmethod
    def from_addresses(cls, *, proxy: str = "", warp_proxy: str = "") -> EgressRegistry:
        """Build the single-instance registry from configured addresses.

        An unconfigured address drops that endpoint, which is what makes the dev/test
        environment (no proxy, no WARP) fall through to DIRECT.
        """
        return cls(
            [
                EgressEndpoint(DIRECT_ID, Egress.DIRECT, ""),
                EgressEndpoint(DEFAULT_WARP_ID, Egress.WARP, warp_proxy),
                EgressEndpoint(DEFAULT_PROXY_ID, Egress.PROXY, proxy),
            ]
        )

    def get(self, egress_id: EgressId) -> EgressEndpoint | None:
        return self._by_id.get(egress_id)

    def all(self) -> tuple[EgressEndpoint, ...]:
        return tuple(self._endpoints)

    def of_kind(self, kind: Egress) -> tuple[EgressEndpoint, ...]:
        return tuple(e for e in self._endpoints if e.kind is kind)

    def plan(
        self,
        platform: str,
        *,
        size_bytes: int | None = None,
        metadata_only: bool = False,
        warp_max_bytes: int = WARP_MAX_DOWNLOAD_BYTES,
    ) -> tuple[EgressEndpoint, ...]:
        """The ordered, *configured* endpoints to try for this request.

        Kinds with no configured endpoint are skipped rather than attempted, so a
        deployment without a proxy simply never plans one.
        """
        kinds = plan_egress(
            platform,
            size_bytes=size_bytes,
            metadata_only=metadata_only,
            warp_max_bytes=warp_max_bytes,
        )
        planned: list[EgressEndpoint] = []
        for kind in kinds:
            planned.extend(self.of_kind(kind))
        return tuple(planned)
