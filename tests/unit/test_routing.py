"""Per-platform egress routing policy (infrastructure.downloader.routing)."""

from __future__ import annotations

from infrastructure.downloader.routing import PROTECTED_PLATFORMS, Egress, plan_egress


def test_protected_platform_prefers_proxy_then_warp() -> None:
    assert "youtube" in PROTECTED_PLATFORMS
    assert plan_egress("youtube") == (Egress.PROXY, Egress.WARP)


def test_protected_platform_metadata_is_proxy_only() -> None:
    # Metadata (extraction) must never fall back to WARP or DIRECT: the account
    # cookies ride along with it and the session stays pinned to one egress IP.
    assert plan_egress("youtube", metadata_only=True) == (Egress.PROXY,)


def test_metadata_only_does_not_change_unprotected_platforms() -> None:
    assert plan_egress("tiktok", metadata_only=True) == (Egress.DIRECT,)


def test_unprotected_platforms_go_direct() -> None:
    # Verified 2026-07-16: these work from the datacenter IP without a proxy.
    for platform in ("tiktok", "facebook", "instagram", "twitter", "generic"):
        assert plan_egress(platform) == (Egress.DIRECT,)


def test_size_bytes_is_accepted_and_currently_ignored() -> None:
    # Wired for a future size-based rule; must not change routing today.
    assert plan_egress("youtube", size_bytes=10) == plan_egress("youtube", size_bytes=10**9)
    assert plan_egress("tiktok", size_bytes=10**9) == (Egress.DIRECT,)
