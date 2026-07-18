"""Per-platform egress routing policy (infrastructure.downloader.routing)."""

from __future__ import annotations

from infrastructure.downloader.routing import (
    DEFAULT_PROXY_ID,
    DEFAULT_WARP_ID,
    DIRECT_ID,
    PROTECTED_PLATFORMS,
    WARP_MAX_DOWNLOAD_BYTES,
    Egress,
    EgressEndpoint,
    EgressRegistry,
    plan_egress,
)

_MB = 1024 * 1024


def _registry() -> EgressRegistry:
    return EgressRegistry.from_addresses(
        proxy="http://u:p@res.example:7577", warp_proxy="socks5://warp-lb:1080"
    )


def test_registry_resolves_plan_to_identified_endpoints() -> None:
    # Cookie affinity pins to a concrete endpoint id, so a plan must yield ids, not kinds.
    reg = _registry()
    assert [e.id for e in reg.plan("youtube", metadata_only=True)] == [DEFAULT_WARP_ID]
    assert [e.id for e in reg.plan("youtube", size_bytes=20 * _MB)] == [
        DEFAULT_WARP_ID,
        DEFAULT_PROXY_ID,
    ]
    assert [e.id for e in reg.plan("youtube", size_bytes=900 * _MB)] == [
        DEFAULT_PROXY_ID,
        DEFAULT_WARP_ID,
    ]
    assert [e.id for e in reg.plan("tiktok")] == [DIRECT_ID]


def test_registry_carries_the_address_and_kind_for_each_endpoint() -> None:
    warp = _registry().get(DEFAULT_WARP_ID)
    assert warp is not None
    assert warp.kind is Egress.WARP
    assert warp.address == "socks5://warp-lb:1080"


def test_unconfigured_endpoints_are_dropped_not_planned() -> None:
    # Dev/test has no proxy or WARP: the plan is empty and the provider falls back to DIRECT.
    bare = EgressRegistry.from_addresses()
    assert bare.plan("youtube", metadata_only=True) == ()
    assert [e.id for e in bare.plan("tiktok")] == [DIRECT_ID]


def test_multiple_instances_of_a_kind_are_all_offered() -> None:
    # The point of the refactor: adding warp-2 is a registry entry, nothing else.
    reg = EgressRegistry(
        [
            EgressEndpoint(DIRECT_ID, Egress.DIRECT, ""),
            EgressEndpoint("warp-1", Egress.WARP, "socks5://warp-1:1080"),
            EgressEndpoint("warp-2", Egress.WARP, "socks5://warp-2:1080"),
        ]
    )
    assert [e.id for e in reg.plan("youtube", metadata_only=True)] == ["warp-1", "warp-2"]


def test_disabled_endpoint_is_never_planned() -> None:
    reg = EgressRegistry(
        [
            EgressEndpoint(DIRECT_ID, Egress.DIRECT, ""),
            EgressEndpoint("warp-1", Egress.WARP, "socks5://warp-1:1080", enabled=False),
        ]
    )
    assert reg.plan("youtube", metadata_only=True) == ()


def test_unprotected_platforms_go_direct() -> None:
    # Verified 2026-07-16: these work from the datacenter IP without a proxy.
    for platform in ("tiktok", "facebook", "instagram", "twitter", "generic"):
        assert plan_egress(platform) == (Egress.DIRECT,)


def test_protected_platform_metadata_is_warp_only() -> None:
    # 2026-07-18: the residential proxy is walled per-video by YouTube while WARP
    # extracts cleanly, so metadata goes over WARP and nothing else.
    assert "youtube" in PROTECTED_PLATFORMS
    assert plan_egress("youtube", metadata_only=True) == (Egress.WARP,)


def test_metadata_only_leaves_unprotected_platforms_direct() -> None:
    assert plan_egress("tiktok", metadata_only=True) == (Egress.DIRECT,)


def test_small_download_prefers_warp_with_proxy_fallback() -> None:
    assert plan_egress("youtube", size_bytes=10 * _MB) == (Egress.WARP, Egress.PROXY)


def test_large_download_prefers_proxy_with_warp_fallback() -> None:
    # WARP is bandwidth-capped and cannot use aria2c — big files go over the proxy.
    assert plan_egress("youtube", size_bytes=900 * _MB) == (Egress.PROXY, Egress.WARP)


def test_threshold_boundary_is_inclusive_for_warp() -> None:
    # "<= 500 MB over WARP": exactly at the threshold stays on WARP; one byte more flips.
    at = plan_egress("youtube", size_bytes=WARP_MAX_DOWNLOAD_BYTES)
    over = plan_egress("youtube", size_bytes=WARP_MAX_DOWNLOAD_BYTES + 1)
    assert at == (Egress.WARP, Egress.PROXY)
    assert over == (Egress.PROXY, Egress.WARP)


def test_unknown_size_is_treated_as_small() -> None:
    assert plan_egress("youtube", size_bytes=None) == (Egress.WARP, Egress.PROXY)


def test_threshold_is_overridable_without_code_change() -> None:
    # Wired to YTDLP_WARP_MAX_DOWNLOAD_MB via core.config → YtdlpProvider.
    assert plan_egress("youtube", size_bytes=100 * _MB, warp_max_bytes=50 * _MB) == (
        Egress.PROXY,
        Egress.WARP,
    )
    assert plan_egress("youtube", size_bytes=100 * _MB, warp_max_bytes=200 * _MB) == (
        Egress.WARP,
        Egress.PROXY,
    )


def test_default_threshold_is_500_mb() -> None:
    assert WARP_MAX_DOWNLOAD_BYTES == 500 * _MB
