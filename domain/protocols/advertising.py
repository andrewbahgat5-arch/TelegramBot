"""Advertising ports (MASTER_PLAN Component 9.2 ``AdService``, Sprint 9 + 9.5, flow 16.7).

The ad pipeline never touches the Telegram client or the signing concrete directly —
it depends on these ports, satisfied by adapters wired at the composition roots
(Section 8.2):

* :class:`AdSenderProtocol` — send one ad (``fields`` mode: text/photo/video/document/
  audio/animation with an optional multi-button keyboard) or ``copy`` a stored message
  (rich content). Implemented by ``infrastructure/telegram/ad_sender.py``.
* :class:`AdClickSignerProtocol` — pack the signed ``callback_data`` for an ad's click
  button (optionally per button). Implemented by ``bot/callbacks/factory.py``.
* :class:`AdShowProtocol` — the post-delivery hook ``DownloadService`` calls after a
  file is delivered (Task 9.3), extended in 9.5 with placement + audience context.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AdButtonSpec:
    """One inline button to render under an ad (Sprint 9.5 multi-button).

    A ``url`` renders a Telegram **URL button** that opens the destination directly
    (preferred, #31 — no extra step). A ``callback_data`` renders a callback button (used
    for click tracking; reserved for a future redirect-based tracked mode). Exactly one
    should be set; ``url`` wins if both are present.
    """

    text: str
    url: str | None = None
    callback_data: str | None = None
    row: int = 0


class AdSenderProtocol(Protocol):
    async def send_ad(
        self,
        chat_id: int,
        *,
        ad_type: str,
        text: str | None,
        media_file_id: str | None,
        buttons: Sequence[AdButtonSpec],
        parse_mode: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> None:
        """Send one ``fields``-mode ad to ``chat_id``.

        ``ad_type`` selects the send method (text/photo/video/document/audio/animation).
        ``buttons`` are laid out into rows (`AdButtonSpec.row`); empty → no keyboard.
        ``reply_to_message_id`` attaches the ad directly under the delivered media (#30).
        """
        ...

    async def copy_ad(
        self,
        chat_id: int,
        *,
        from_chat_id: int,
        message_id: int,
        buttons: Sequence[AdButtonSpec],
        reply_to_message_id: int | None = None,
    ) -> None:
        """Deliver a ``copy``-mode ad by copying a stored message (16.7, D-042).

        ``copyMessage`` reproduces the source's media + caption + formatting but drops
        its inline keyboard, so ``buttons`` are re-attached here. ``reply_to_message_id``
        attaches the ad directly under the delivered media (#30).
        """
        ...

    async def send_rich_ad(
        self,
        chat_id: int,
        *,
        markdown: str,
        buttons: Sequence[AdButtonSpec],
        reply_to_message_id: int | None = None,
    ) -> None:
        """Deliver a ``rich``-mode ad via ``sendRichMessage`` (Rich Markdown source).

        Renders the full Rich Message format (headings, lists, collapsible blocks, image
        blocks, tables, plus standard inline formatting) that classic ``parse_mode`` cannot.
        May raise if the Bot API server does not support rich messages — the caller falls
        back to a classic send so an ad never silently fails to deliver.
        """
        ...


class AdClickSignerProtocol(Protocol):
    def pack_ad_click(self, ad_id: int, button_id: int | None = None) -> str:
        """Return the signed ``callback_data`` for an ad/button click button (14.2)."""
        ...


class AdEventRecorderProtocol(Protocol):
    """Records per-event ad analytics **off** the delivery hot path (Sprint 9.5.9, D-052).

    Both methods are **synchronous and non-blocking** by contract: they hand the event
    off (e.g. schedule a background write) and return immediately, so an ``ad_events``
    INSERT never adds latency to ad delivery. Recording is best-effort — the
    ``advertisements`` / ``ad_buttons`` counters remain the source of truth (D-045).
    """

    def record_impression(
        self, *, advertisement_id: int, user_id: int | None, placement: str | None
    ) -> None: ...

    def record_click(
        self, *, advertisement_id: int, user_id: int | None, button_id: int | None
    ) -> None: ...


class AdShowProtocol(Protocol):
    async def maybe_show(
        self,
        *,
        chat_id: int,
        role: str,
        is_premium: bool,
        premium_expires_at: datetime.datetime | None,
        total_downloads: int,
        language: str | None = None,
        telegram_id: int | None = None,
        user_row_id: int | None = None,
        placement: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> bool:
        """Select and deliver an ad after a successful download (flow 16.7, D-010).

        ``total_downloads`` is the user's **post-increment** lifetime count (D-010).
        ``placement`` defaults to the Sprint 9 post-download placement.
        ``reply_to_message_id`` attaches the ad under the delivered media (#30).
        Best-effort: a delivery failure is logged and swallowed so it never breaks
        the download.
        """
        ...
