"""CaptionAdMixer — the single place that injects a caption-layer ad into media captions.

Two-layer ads (UX): a *caption ad* is an ad's text + inline buttons rendered **inside a
delivered media's own caption** (same message), because Telegram captions cannot carry
extra media. Every media-send site (fresh download, waiter fan-out, cache hit, history
resend, the analysis screen) routes its caption through :meth:`decorate` so the injection
logic lives in exactly one place — no per-handler duplication.

Layer-clean: this stays in ``services`` (never imports ``bot``/aiogram). It returns the
final caption string plus the ad's :class:`~domain.protocols.advertising.AdButtonSpec`
buttons; the transport layer (``TelegramFileSender``) turns those into an inline keyboard,
reusing the same builder the ad sender uses.
"""

from __future__ import annotations

import datetime
from typing import Any

from core.logging import get_logger
from domain.protocols.advertising import AdButtonSpec
from services.ad_service import AdService

_log = get_logger("services.caption_ad_mixer")

# Telegram's hard limit for a media caption. The ad block is kept intact; the base caption
# (usually a short media title) is trimmed first if the two together would overflow.
_CAPTION_LIMIT = 1024


class CaptionAdMixer:
    """Appends the due caption ad's text + buttons to a media caption (best-effort)."""

    def __init__(self, ad_service: AdService) -> None:
        self._ads = ad_service

    async def decorate(
        self,
        base_caption: str | None,
        *,
        role: str,
        is_premium: bool,
        premium_expires_at: datetime.datetime | None,
        total_downloads: int,
        language: str | None = None,
        telegram_id: int | None = None,
        user_row_id: int | None = None,
    ) -> tuple[str | None, tuple[AdButtonSpec, ...]]:
        """Return ``(caption, buttons)`` with the caption ad merged in, or unchanged.

        Never raises: an ad must never break a delivery, so any failure falls back to the
        original caption with no buttons (mirrors ``AdService._deliver``'s best-effort rule).
        """
        try:
            ad = await self._ads.select_caption_ad(
                role=role,
                is_premium=is_premium,
                premium_expires_at=premium_expires_at,
                total_downloads=total_downloads,
                language=language,
                telegram_id=telegram_id,
                user_row_id=user_row_id,
            )
        except Exception as exc:  # never let ad selection break a completed download
            _log.warning("caption_ad_select_failed", error=str(exc))
            return base_caption, ()
        if ad is None:
            return base_caption, ()
        return _merge(base_caption, ad.text), ad.buttons

    async def decorate_for_user(
        self, user: Any, base_caption: str | None, total_downloads: int
    ) -> tuple[str | None, tuple[AdButtonSpec, ...]]:
        """Convenience wrapper: pull the audience fields off a ``User``/``UserSnapshot``.

        Duck-typed (``Any``) — both the ORM ``User`` and the frozen ``UserSnapshot`` expose
        ``id``/``telegram_id``/``role``/``is_premium``/``total_downloads`` (+ optional
        ``language``/``premium_expires_at``), which is all the audience engine reads.
        """
        return await self.decorate(
            base_caption,
            role=str(user.role),
            is_premium=bool(user.is_premium),
            premium_expires_at=getattr(user, "premium_expires_at", None),
            total_downloads=total_downloads,
            language=getattr(user, "language", None),
            telegram_id=user.telegram_id,
            user_row_id=user.id,
        )


def _merge(base_caption: str | None, ad_text: str) -> str:
    """Fit ``base_caption`` + a two-newline-separated ad block into the caption limit.

    With no base caption (e.g. a history resend has no title) the ad text stands alone —
    no leading blank lines.
    """
    base = (base_caption or "").strip()
    if not base:
        return ad_text[:_CAPTION_LIMIT]
    ad_block = f"\n\n{ad_text}"
    room = _CAPTION_LIMIT - len(ad_block)
    return (base[: max(0, room)] + ad_block)[:_CAPTION_LIMIT]
