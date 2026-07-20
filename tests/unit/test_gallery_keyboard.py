"""Gallery flow: browse → select → media type → quality, and the Back chain.

The Back chain is the part that has broken before, so each hop is pinned explicitly.
"""

from __future__ import annotations

from bot.callbacks.factory import CallbackSigner
from bot.keyboards.gallery import (
    browse_caption,
    build_browse_keyboard,
    build_item_keyboard,
    gallery_back_callback,
    item_back_callback,
    item_caption,
)
from bot.keyboards.quality_select import build_quality_keyboard
from domain.entities.media import CarouselItem, MediaFormatOption, MediaInfo
from domain.enums import MediaFormat, Quality

_SIGNER = CallbackSigner("k")
_POST = 77  # the post's media_id (the gallery container)


def _items() -> tuple[CarouselItem, ...]:
    return (
        CarouselItem(1, "Clip one", MediaFormat.VIDEO, height=1080, thumbnail_url="u1",
                     has_audio=True),
        CarouselItem(2, "A photo", MediaFormat.IMAGE, thumbnail_url="u2"),
        CarouselItem(3, "A track", MediaFormat.AUDIO, thumbnail_url="u3"),
    )


def _ops(markup: object) -> list[str]:
    return [
        _SIGNER.unpack(b.callback_data).language
        for row in markup.inline_keyboard  # type: ignore[attr-defined]
        for b in row
    ]


# --- Step 1: the browser is for browsing, nothing else ---------------------
def test_browse_screen_shows_only_navigation_and_select() -> None:
    """No Video/Audio/Quality/Download on the browsing screen — its single job is
    choosing WHICH item, so every other button is noise at that moment."""
    kb = build_browse_keyboard(_POST, _items(), 1, _SIGNER, "en")
    assert _ops(kb) == ["n", "n", "n", "s"]  # prev, counter, next, select
    assert len(kb.inline_keyboard) == 2


def test_browse_navigation_wraps_in_both_directions() -> None:
    items = _items()
    first = build_browse_keyboard(_POST, items, 1, _SIGNER, "en").inline_keyboard[0]
    last = build_browse_keyboard(_POST, items, 3, _SIGNER, "en").inline_keyboard[0]
    assert _SIGNER.unpack(first[0].callback_data).arg == 3  # Previous from first → last
    assert _SIGNER.unpack(last[2].callback_data).arg == 1  # Next from last → first


def test_browse_caption_states_the_position() -> None:
    assert "Item 2 / 3" in browse_caption(_items()[1], 3, "en")


def test_select_button_targets_the_item_being_viewed() -> None:
    kb = build_browse_keyboard(_POST, _items(), 2, _SIGNER, "en")
    select = _SIGNER.unpack(kb.inline_keyboard[1][0].callback_data)
    assert select.language == "s" and select.arg == 2 and select.media_id == _POST


# --- Step 2: the selected item's actions depend on its kind ----------------
def test_video_item_offers_video_audio_and_back() -> None:
    kb = build_item_keyboard(_POST, _items()[0], _SIGNER, "en")
    assert _ops(kb) == ["v", "a", "n"]


def test_image_item_offers_only_the_image_and_back() -> None:
    kb = build_item_keyboard(_POST, _items()[1], _SIGNER, "en")
    assert _ops(kb) == ["i", "n"]


def test_audio_item_offers_only_audio_and_back() -> None:
    kb = build_item_keyboard(_POST, _items()[2], _SIGNER, "en")
    assert _ops(kb) == ["a", "n"]


# --- The Back chain: one step each, never a dead end -----------------------
def test_back_from_selected_item_returns_to_the_browser_at_that_item() -> None:
    """The browsing session must survive: same post, same item, browse screen."""
    kb = build_item_keyboard(_POST, _items()[2], _SIGNER, "en")
    back = _SIGNER.unpack(kb.inline_keyboard[-1][0].callback_data)
    assert back.action == "g" and back.language == "n"
    assert back.media_id == _POST and back.arg == 3


def test_back_from_quality_returns_to_the_selected_item_screen() -> None:
    """REGRESSION: Back used to walk to the ITEM's own format screen, so the browser —
    position, preview, Previous/Next — vanished and the link had to be resent. It must
    carry the POST's media_id and the item index, one step back up the chain.
    """
    info = MediaInfo(
        platform="instagram",
        video_id="x#4",
        title="t",
        source_url="https://www.instagram.com/p/X/",
        formats=(MediaFormatOption(MediaFormat.VIDEO, Quality.P720, 1, "f"),),
    )
    kb = build_quality_keyboard(
        999,  # the ITEM's media_id — deliberately different from the post's
        MediaFormat.VIDEO,
        info,
        _SIGNER,
        "en",
        back_callback=item_back_callback(_POST, 4, _SIGNER),
    )
    back = _SIGNER.unpack(kb.inline_keyboard[-1][0].callback_data)
    assert back.action == "g"  # into the gallery, not the plain format screen
    assert back.media_id == _POST  # the POST, never the item
    assert back.arg == 4  # at the very item it was opened from
    assert back.language == "s"  # the selected-item screen, one step back


def test_the_two_back_targets_are_different_steps() -> None:
    """Quality→selected and selected→browse must not collapse into the same hop."""
    assert item_back_callback(_POST, 2, _SIGNER) != gallery_back_callback(_POST, 2, _SIGNER)


def test_quality_screen_outside_a_gallery_keeps_the_plain_back() -> None:
    """The single-media flow is untouched: Back still returns to Video/Audio."""
    info = MediaInfo(
        platform="youtube",
        video_id="v",
        title="t",
        source_url="u",
        formats=(MediaFormatOption(MediaFormat.VIDEO, Quality.P720, 1, "f"),),
    )
    kb = build_quality_keyboard(55, MediaFormat.VIDEO, info, _SIGNER, "en")
    back = _SIGNER.unpack(kb.inline_keyboard[-1][0].callback_data)
    assert back.action == "b" and back.media_id == 55


# --- audio must only be offered when the item actually HAS audio -----------
def _video_item(*, has_audio: bool) -> CarouselItem:
    return CarouselItem(
        1, "Clip", MediaFormat.VIDEO, height=1080, thumbnail_url="u", has_audio=has_audio
    )


def test_video_with_audio_offers_both_video_and_audio() -> None:
    kb = build_item_keyboard(_POST, _video_item(has_audio=True), _SIGNER, "en")
    assert _ops(kb) == ["v", "a", "n"]


def test_video_without_audio_hides_the_audio_button() -> None:
    """REGRESSION: Instagram serves anonymous carousel items as "video only" on every
    format — yt-dlp's -F marks all 11 that way and a download confirms no audio stream.
    Offering Audio there produced "No downloadable formats were found" whatever the user
    pressed: a dead end. The button must not be there at all.
    """
    kb = build_item_keyboard(_POST, _video_item(has_audio=False), _SIGNER, "en")
    assert _ops(kb) == ["v", "n"]  # video + back, no audio
    assert "a" not in _ops(kb)


def test_caption_warns_when_a_video_has_no_audio() -> None:
    """Say it up front rather than letting the user find out from a silent file."""
    with_audio = item_caption(_video_item(has_audio=True), 5, "en")
    without = item_caption(_video_item(has_audio=False), 5, "en")
    assert "no audio track" in without.lower()
    assert "no audio track" not in with_audio.lower()
