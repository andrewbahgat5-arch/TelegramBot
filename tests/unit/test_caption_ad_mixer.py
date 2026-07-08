"""Unit tests for the caption-ad mixer (two-layer ads)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from domain.protocols.advertising import AdButtonSpec
from services.ad_service import CaptionAd
from services.caption_ad_mixer import CaptionAdMixer, _merge

_CTX: dict[str, Any] = {
    "role": "user",
    "is_premium": False,
    "premium_expires_at": None,
    "total_downloads": 1,
}


class _StubAds:
    def __init__(self, ad: CaptionAd | None) -> None:
        self._ad = ad
        self.calls = 0

    async def select_caption_ad(self, **_kw: Any) -> CaptionAd | None:
        self.calls += 1
        return self._ad


async def test_decorate_appends_text_and_returns_buttons() -> None:
    ad = CaptionAd(text="Subscribe!", buttons=(AdButtonSpec("Go", url="https://x"),))
    caption, buttons = await CaptionAdMixer(_StubAds(ad)).decorate("Title", **_CTX)  # type: ignore[arg-type]
    assert caption == "Title\n\nSubscribe!"
    assert buttons == ad.buttons


async def test_decorate_no_ad_leaves_caption_unchanged() -> None:
    caption, buttons = await CaptionAdMixer(_StubAds(None)).decorate("Title", **_CTX)  # type: ignore[arg-type]
    assert caption == "Title"
    assert buttons == ()


async def test_decorate_empty_base_uses_ad_text_alone() -> None:
    ad = CaptionAd(text="Subscribe!", buttons=())
    caption, _ = await CaptionAdMixer(_StubAds(ad)).decorate(None, **_CTX)  # type: ignore[arg-type]
    assert caption == "Subscribe!"  # no leading blank lines


async def test_decorate_swallows_selection_errors() -> None:
    class _Boom:
        async def select_caption_ad(self, **_kw: Any) -> CaptionAd | None:
            raise RuntimeError("selection blew up")

    caption, buttons = await CaptionAdMixer(_Boom()).decorate("Title", **_CTX)  # type: ignore[arg-type]
    assert caption == "Title"  # an ad must never break a delivery
    assert buttons == ()


async def test_decorate_for_user_pulls_audience_fields() -> None:
    ad = CaptionAd(text="Hi", buttons=())
    user = SimpleNamespace(
        id=1,
        telegram_id=5,
        role="user",
        is_premium=False,
        premium_expires_at=None,
        language="en",
        total_downloads=3,
    )
    caption, _ = await CaptionAdMixer(_StubAds(ad)).decorate_for_user(user, "T", 3)
    assert caption == "T\n\nHi"


def test_merge_keeps_ad_block_within_caption_limit() -> None:
    out = _merge("Title", "a" * 1100)
    assert len(out) <= 1024
    assert out.endswith("a")  # the ad block is preserved (base trimmed first)
