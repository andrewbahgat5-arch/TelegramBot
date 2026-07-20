"""Multi-media gallery: browse a multi-item post inside ONE message.

A link carrying several media items (an Instagram carousel, and anything else an
extractor returns as a playlist) is presented as a gallery rather than a wall of
messages: one photo message whose preview, caption and buttons are edited in place.

The flow is one purpose per screen:

    Browse  ──✅ Select──▶  Selected item  ──🎥/🎵/🖼──▶  Quality  ──▶  Download
      ▲                          │                          │
      └──────── ⬅️ Back ─────────┘◀────────── ⬅️ Back ──────┘

Browsing shows ONLY navigation and one primary action, so the screen has a single job:
find the item you want. Media-type and quality choices live on their own screens.

Back always walks exactly one step back up that chain and never dead-ends: the gallery
is rebuilt at the very item it was opened from, so the browsing session survives.

The action row is derived from the item's ``kind``, never from the platform — a video
offers video/audio, a photo offers the image, an audio-only item offers audio. ``kind``
is computed from the options the item actually yields, so a new extractor returning
some novel shape still lands on a sensible row.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.callbacks.factory import CallbackSigner
from core.i18n import translate
from domain.entities.media import CarouselItem
from domain.enums import MediaFormat

# Gallery sub-ops (see CallbackSigner.pack_gallery).
OP_BROWSE = "n"  # show the browser at an item
OP_SELECT = "s"  # show the chosen item's media-type actions
OP_VIDEO = "v"
OP_AUDIO = "a"
OP_IMAGE = "i"


def _position(index: int, total: int, locale: str) -> str:
    return translate("gallery.position", locale, index=index, total=total)


def _titled(item: CarouselItem, total: int, locale: str, header: str, title: str) -> str:
    lines = [header, _position(item.index, total, locale)]
    label = (item.title or title).strip()
    if label:
        lines.append(label[:120])
    return "\n".join(lines)


def browse_caption(
    item: CarouselItem,
    total: int,
    locale: str,
    title: str = "",
    source_total: int | None = None,
) -> str:
    """Browsing screen: position first, because that is what the user is tracking.

    ``source_total`` is how many items the SOURCE has, when that exceeds what we list.
    A playlist can hold thousands; showing the first 50 is fine, silently pretending
    there are only 50 is not.
    """
    caption = _titled(item, total, locale, translate("gallery.browse", locale), title)
    if source_total and source_total > total:
        note = translate("gallery.truncated", locale, shown=total, total=source_total)
        caption = f"{caption}\n{note}"
    return caption


def item_caption(item: CarouselItem, total: int, locale: str, title: str = "") -> str:
    """Selected-item screen: now it is about what to do with this item.

    A video with no obtainable audio says so, rather than letting the user discover it
    only after downloading a silent file.
    """
    caption = _titled(item, total, locale, translate("gallery.choose", locale), title)
    if item.kind is MediaFormat.VIDEO and not item.has_audio:
        note = translate("gallery.no_audio", locale)
        caption = f"{caption}\n\n{note}"
    return caption


def build_browse_keyboard(
    media_id: int,
    items: tuple[CarouselItem, ...],
    index: int,
    signer: CallbackSigner,
    locale: str,
) -> InlineKeyboardMarkup:
    """Navigation + one primary action. Nothing else belongs on this screen.

    Navigation wraps around: Next on the last item returns to the first. Wrapping beats
    disabling, which in Telegram means either a dead button or a row that changes width
    as you page — both read as breakage.
    """
    total = len(items)
    builder = InlineKeyboardBuilder()

    if total > 1:
        prev_index = total if index == 1 else index - 1
        next_index = 1 if index == total else index + 1
        builder.row(
            InlineKeyboardButton(
                text=translate("gallery.previous", locale),
                callback_data=signer.pack_gallery(media_id, prev_index, OP_BROWSE),
            ),
            InlineKeyboardButton(
                text=_position(index, total, locale),
                # Telegram has no inert element, so the counter is a button that
                # re-renders the current item — a deliberate no-op.
                callback_data=signer.pack_gallery(media_id, index, OP_BROWSE),
            ),
            InlineKeyboardButton(
                text=translate("gallery.next", locale),
                callback_data=signer.pack_gallery(media_id, next_index, OP_BROWSE),
            ),
        )

    builder.row(
        InlineKeyboardButton(
            text=translate("gallery.select", locale),
            callback_data=signer.pack_gallery(media_id, index, OP_SELECT),
        )
    )
    return builder.as_markup()


def build_item_keyboard(
    media_id: int,
    item: CarouselItem,
    signer: CallbackSigner,
    locale: str,
) -> InlineKeyboardMarkup:
    """What can be done with the selected item, plus Back to the browser."""
    builder = InlineKeyboardBuilder()
    if item.kind is MediaFormat.VIDEO:
        buttons = [
            InlineKeyboardButton(
                text=translate("gallery.download_video", locale),
                callback_data=signer.pack_gallery(media_id, item.index, OP_VIDEO),
            )
        ]
        # Audio only when the item actually HAS an audio track. Some sources serve
        # video-only renditions — Instagram marks every anonymous carousel format
        # "video only" — and an Audio button there is a dead end that answers
        # "no downloadable formats" no matter what the user does.
        if item.has_audio:
            buttons.append(
                InlineKeyboardButton(
                    text=translate("gallery.download_audio", locale),
                    callback_data=signer.pack_gallery(media_id, item.index, OP_AUDIO),
                )
            )
        builder.row(*buttons)
    elif item.kind is MediaFormat.AUDIO:
        builder.row(
            InlineKeyboardButton(
                text=translate("gallery.download_audio", locale),
                callback_data=signer.pack_gallery(media_id, item.index, OP_AUDIO),
            )
        )
    else:  # IMAGE — nothing to choose; the button downloads.
        builder.row(
            InlineKeyboardButton(
                text=translate("gallery.download_image", locale),
                callback_data=signer.pack_gallery(media_id, item.index, OP_IMAGE),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=translate("common.back", locale),
            callback_data=gallery_back_callback(media_id, item.index, signer),
        )
    )
    return builder.as_markup()


def gallery_back_callback(media_id: int, index: int, signer: CallbackSigner) -> str:
    """Back target for the selected-item screen → the BROWSER at that item."""
    return signer.pack_gallery(media_id, index, OP_BROWSE)


def item_back_callback(media_id: int, index: int, signer: CallbackSigner) -> str:
    """Back target for a quality screen → the SELECTED-ITEM screen it was opened from.

    One step back up the chain, not two: jumping straight to the browser would make the
    user re-select the item just to try the other media type.
    """
    return signer.pack_gallery(media_id, index, OP_SELECT)
