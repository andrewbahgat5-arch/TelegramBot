"""AdService (MASTER_PLAN Component 9.2, Sprint 9 + 9.5, flow 16.7 — LOCKED D-010).

Owns advertisement selection, delivery, and the admin CRUD surface:

* :meth:`maybe_show` — the placement-aware post-action selection algorithm. Walks the
  active candidates for a placement highest-priority-first, asks :class:`AudienceService`
  whether each matches the viewer (Sprint 9.5 first-class targeting, with a dual-read
  fallback to the Sprint 9 ``target_role`` for legacy ads), and delivers the first whose
  frequency lands on this (post-increment) download. Best-effort — a send failure is
  logged and swallowed so it never breaks an already-completed download.
* :meth:`_deliver` — ``fields`` mode (programmatic text/media + multi-button keyboard)
  or ``copy`` mode (``copyMessage`` of a stored rich message), per ad.
* :meth:`record_click` — increments ad + per-button click counters; returns the link.
* Admin CRUD: ad create/list/get/edit/toggle/delete/stats/global, button management,
  and ``/ad_preview`` (Tasks 9.2 + 9.5.2/9.5.4/9.5.8).

Concretes (signer, Telegram transport) are injected as protocols, so this service stays
in the ``services`` layer (never imports ``bot``/``infrastructure``, Section 8).
"""

from __future__ import annotations

import datetime
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from core import metrics
from core.logging import get_logger
from core.timeparse import parse_iso_datetime
from domain.enums import (
    UNLIMITED_ROLES,
    AdDeliveryMode,
    AdPlacement,
    AdType,
    AudienceMode,
)
from domain.exceptions import AppError
from domain.protocols.advertising import (
    AdButtonSpec,
    AdClickSignerProtocol,
    AdEventRecorderProtocol,
    AdSenderProtocol,
)
from domain.protocols.repositories import AdButtonRepositoryProtocol, AdRepositoryProtocol
from services.audience_service import AudienceContext, AudienceService
from services.settings_service import SettingNotFoundError, SettingsService

_log = get_logger("services.ad_service")

_AD_TARGET_ROLES = frozenset({"user", "premium"})
_UNTARGETED_TOKENS = frozenset({"none", "all", "any", ""})

# /ad_create + /ad_edit field aliases → ``advertisements`` columns.
_FIELD_TO_COLUMN: dict[str, str] = {
    "title": "title",
    "type": "type",
    "text": "content_text",
    "file_id": "content_media_file_id",
    "button_text": "button_text",
    "button_url": "button_url",
    "target": "target_role",
    "language": "target_language",  # language-first ads (each language its own campaigns)
    "every": "show_every_n_downloads",
    "priority": "priority",
    "placement": "placement",
    "delivery": "delivery_mode",
    "audience": "audience_mode",
    "parse_mode": "parse_mode",
    "storage_chat_id": "storage_chat_id",
    "storage_message_id": "storage_message_id",
    "scheduled_at": "scheduled_at",
    "internal_name": "internal_name",  # admin-only metadata (D-058)
    "notes": "internal_notes",
}

_CLEAR_TOKENS = frozenset({"none", "never", ""})
_EDITABLE_FIELDS = frozenset(_FIELD_TO_COLUMN)


class InvalidAdError(AppError):
    """An ad create/edit request is malformed (bad type, missing content, etc.)."""


@dataclass(frozen=True, slots=True)
class AdStats:
    """Aggregate ad counters for ``/ad_stats`` (no id)."""

    total_ads: int
    active_ads: int
    impressions: int
    clicks: int


@dataclass(frozen=True, slots=True)
class CaptionAd:
    """A caption-layer ad resolved to what a media caption can carry: text + buttons.

    Telegram captions cannot embed media, so the caption layer only ever renders the ad's
    ``content_text`` plus its inline buttons (built once, reused per recipient in a fan-out).
    """

    text: str
    buttons: tuple[AdButtonSpec, ...]


@dataclass(frozen=True, slots=True)
class AdBroadcastPlan:
    """A pre-resolved ad ready to deliver to many recipients (Sprint 9.5 ad broadcast).

    Built once per broadcast so the worker re-sends to each recipient with no per-send
    DB read (buttons + content are static for the ad).
    """

    delivery_mode: str
    ad_type: str
    content_text: str | None
    content_media_file_id: str | None
    parse_mode: str | None
    storage_chat_id: int | None
    storage_message_id: int | None
    buttons: tuple[AdButtonSpec, ...]


async def deliver_plan(sender: AdSenderProtocol, plan: AdBroadcastPlan, chat_id: int) -> None:
    """Deliver a prepared ad to one chat (``rich`` / ``copy`` / ``fields`` mode)."""
    if plan.delivery_mode == AdDeliveryMode.RICH.value and plan.content_text:
        try:
            await sender.send_rich_ad(chat_id, markdown=plan.content_text, buttons=plan.buttons)
        except Exception as exc:  # rich unsupported → classic text fallback
            _log.warning("ad_broadcast_rich_fallback", chat_id=chat_id, error=str(exc))
            await sender.send_ad(
                chat_id,
                ad_type=AdType.TEXT.value,
                text=plan.content_text,
                media_file_id=None,
                buttons=plan.buttons,
                parse_mode=None,
            )
    elif (
        plan.delivery_mode == AdDeliveryMode.COPY.value
        and plan.storage_chat_id
        and plan.storage_message_id
    ):
        await sender.copy_ad(
            chat_id,
            from_chat_id=plan.storage_chat_id,
            message_id=plan.storage_message_id,
            buttons=plan.buttons,
        )
    else:
        await sender.send_ad(
            chat_id,
            ad_type=plan.ad_type,
            text=plan.content_text,
            media_file_id=plan.content_media_file_id,
            buttons=plan.buttons,
            parse_mode=plan.parse_mode,
        )


class AdService:
    def __init__(
        self,
        *,
        ad_repo: AdRepositoryProtocol[Any],
        settings: SettingsService,
        sender: AdSenderProtocol,
        signer: AdClickSignerProtocol,
        button_repo: AdButtonRepositoryProtocol[Any],
        audience: AudienceService,
        event_recorder: AdEventRecorderProtocol | None = None,
    ) -> None:
        self._ads = ad_repo
        self._settings = settings
        self._sender = sender
        self._signer = signer
        self._buttons = button_repo
        self._audience = audience
        self._events = event_recorder

    # --- delivery (flow 16.7 + Sprint 9.5 placement/audience) ------------
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
        """Select and deliver a standalone ad at ``placement`` after a user action.

        This is the "follow-up message" layer (16.7, D-010): the chosen ad is delivered as
        its own message. The caption layer (:meth:`select_caption_ad`) shares the very same
        selection via :meth:`_select_due_ad`, so audience/scheduling/rotation never diverge.
        """
        place = placement or AdPlacement.POST_DOWNLOAD.value
        if not await self._ads_enabled():
            return False
        if not await self._placement_enabled(place):
            return False
        ctx = self._audience_ctx(
            role, is_premium, premium_expires_at, language, telegram_id, user_row_id
        )
        ad = await self._select_due_ad(place, ctx, total_downloads)
        if ad is None:
            return False
        delivered = await self._deliver(ad, chat_id, reply_to_message_id=reply_to_message_id)
        if delivered and self._events is not None:
            # Off the hot path (D-052): schedules a background ad_events write; the
            # advertisements.impressions counter (in _deliver) stays the source of truth.
            self._events.record_impression(
                advertisement_id=ad.id, user_id=user_row_id, placement=place
            )
        return delivered

    def _audience_ctx(
        self,
        role: str,
        is_premium: bool,
        premium_expires_at: datetime.datetime | None,
        language: str | None,
        telegram_id: int | None,
        user_row_id: int | None,
    ) -> AudienceContext:
        premium = _is_premium_active(is_premium, premium_expires_at)
        return AudienceContext(
            role=role,
            plan="premium" if premium else "free",
            language=language,
            telegram_id=telegram_id or 0,
            user_row_id=user_row_id or 0,
            untargeted_exempt=premium or role in UNLIMITED_ROLES,
        )

    async def _select_due_ad(
        self, place: str, ctx: AudienceContext, total_downloads: int
    ) -> Any | None:
        """The one ad to show at ``place`` for this viewer, or None — the shared selector.

        Walks active candidates in the repo's fair-rotation order (priority DESC, then
        least-recently-shown, #10), skipping not-yet-due (``scheduled_at``), audience
        non-matches, and ads whose ``every-N`` does not land on this download. Returns the
        first eligible ad **without delivering it**, so both the follow-up and caption layers
        reuse the identical logic.
        """
        now = datetime.datetime.now(datetime.UTC)
        for ad in await self._ads.list_active_for_placement(place):
            scheduled_at = getattr(ad, "scheduled_at", None)
            if scheduled_at is not None and scheduled_at > now:  # not yet due (9.5.10)
                continue
            # Language-first ads: a language-targeted ad shows only to that language's
            # viewers (untargeted ads — target_language IS NULL — always match). Mirrors the
            # target_role scalar filter; the exact-match convention matches the audience
            # engine's LANGUAGE dimension (audience_service._rule_hit).
            target_language = getattr(ad, "target_language", None)
            if target_language is not None and target_language != ctx.language:
                continue
            if not await self._audience.matches(ad, ctx):
                continue
            frequency = ad.show_every_n_downloads or 1
            if total_downloads % frequency != 0:  # post-increment modulo (D-010)
                continue
            return ad
        return None

    async def select_caption_ad(
        self,
        *,
        role: str,
        is_premium: bool,
        premium_expires_at: datetime.datetime | None,
        total_downloads: int,
        language: str | None = None,
        telegram_id: int | None = None,
        user_row_id: int | None = None,
    ) -> CaptionAd | None:
        """Pick the caption-layer ad for this viewer as text + buttons (UX: caption ads).

        The caption layer injects an ad's text and inline buttons into a delivered media's
        own caption (Telegram captions cannot hold media, so only text + buttons apply). This
        selects the due ``caption``-placement ad via the shared :meth:`_select_due_ad`,
        records the impression (advancing the impressions counter + ``last_shown_at``
        rotation exactly like a delivered ad), and returns its text + buttons for the mixer
        to render. Returns None when the layer is off, no ad matches, or the ad has no text.
        """
        if not await self._ads_enabled():
            return None
        if not await self._placement_enabled(AdPlacement.CAPTION.value):
            return None
        ctx = self._audience_ctx(
            role, is_premium, premium_expires_at, language, telegram_id, user_row_id
        )
        ad = await self._select_due_ad(AdPlacement.CAPTION.value, ctx, total_downloads)
        if ad is None or not (ad.content_text or "").strip():
            return None
        buttons = await self._build_buttons(ad)
        await self._ads.increment_impressions(ad.id)  # counter + last_shown_at rotation (#10)
        metrics.record_ad_shown()
        if self._events is not None:
            self._events.record_impression(
                advertisement_id=ad.id, user_id=user_row_id, placement=AdPlacement.CAPTION.value
            )
        _log.info("caption_ad_selected", ad_id=ad.id)
        return CaptionAd(text=str(ad.content_text), buttons=tuple(buttons))

    async def _ads_enabled(self) -> bool:
        try:
            enabled: bool = await self._settings.get("ads_enabled")
        except SettingNotFoundError:
            return False
        return bool(enabled)

    async def _placement_enabled(self, placement: str) -> bool:
        try:
            enabled: bool = await self._settings.get(f"ad_placement_{placement}_enabled")
        except SettingNotFoundError:
            # Unconfigured: the Sprint 9 compat placement and the caption layer are on by
            # default (no seed row needed) — the admin's real on/off control for the caption
            # layer is the ad's own Enabled toggle + whether it targets the caption placement.
            return placement in (AdPlacement.POST_DOWNLOAD.value, AdPlacement.CAPTION.value)
        return bool(enabled)

    async def _build_buttons(self, ad: Any) -> list[AdButtonSpec]:
        """Inline buttons for an ad: the ``ad_buttons`` rows, or the legacy single button.

        Buttons render as Telegram **URL buttons** so tapping opens the destination
        directly (#31, no extra step). URL-less rows are skipped. (The signed per-button
        click callback — ``self._signer`` — is retained for a future redirect-based
        tracked mode; URL buttons fire no callback, so per-button clicks are not counted.)
        """
        rows = await self._buttons.list_for_ad(ad.id)
        if rows:
            return [AdButtonSpec(b.text, url=b.url, row=b.row) for b in rows if b.url]
        if ad.button_url and ad.button_text:
            return [AdButtonSpec(ad.button_text, url=ad.button_url)]
        return []

    async def _deliver(
        self, ad: Any, chat_id: int, *, reply_to_message_id: int | None = None
    ) -> bool:
        """Send one ad and record the impression (16.7 steps 5-6). Best-effort."""
        buttons = await self._build_buttons(ad)
        try:
            if ad.delivery_mode == AdDeliveryMode.RICH and ad.content_text:
                await self._send_rich(ad, chat_id, buttons, reply_to_message_id)
            elif (
                ad.delivery_mode == AdDeliveryMode.COPY
                and ad.storage_chat_id
                and ad.storage_message_id
            ):
                await self._sender.copy_ad(
                    chat_id,
                    from_chat_id=ad.storage_chat_id,
                    message_id=ad.storage_message_id,
                    buttons=buttons,
                    reply_to_message_id=reply_to_message_id,
                )
            else:
                await self._sender.send_ad(
                    chat_id,
                    ad_type=ad.type,
                    text=ad.content_text,
                    media_file_id=ad.content_media_file_id,
                    buttons=buttons,
                    parse_mode=ad.parse_mode,
                    reply_to_message_id=reply_to_message_id,
                )
        except Exception as exc:  # an ad must never break a completed action
            _log.warning("ad_delivery_failed", ad_id=ad.id, chat_id=chat_id, error=str(exc))
            return False
        await self._ads.increment_impressions(ad.id)
        metrics.record_ad_shown()
        _log.info("ad_shown", ad_id=ad.id, chat_id=chat_id)
        return True

    async def _send_rich(
        self,
        ad: Any,
        chat_id: int,
        buttons: Sequence[AdButtonSpec],
        reply_to_message_id: int | None,
    ) -> None:
        """Deliver a Rich-Markdown ad, falling back to a classic text send if unsupported."""
        try:
            await self._sender.send_rich_ad(
                chat_id,
                markdown=ad.content_text,
                buttons=buttons,
                reply_to_message_id=reply_to_message_id,
            )
        except Exception as exc:  # Bot API server without rich-message support, etc.
            _log.warning("ad_rich_fallback", ad_id=ad.id, chat_id=chat_id, error=str(exc))
            await self._sender.send_ad(
                chat_id,
                ad_type=AdType.TEXT.value,
                text=ad.content_text,
                media_file_id=None,
                buttons=buttons,
                parse_mode=None,
                reply_to_message_id=reply_to_message_id,
            )

    async def record_click(
        self, ad_id: int, button_id: int | None = None, *, user_row_id: int | None = None
    ) -> str | None:
        """Record an ad/button click; return the destination URL or None (16.7 W6)."""
        ad = await self._ads.get_by_id(ad_id)
        if ad is None:
            return None
        await self._ads.increment_clicks(ad_id)
        if button_id is not None:
            await self._buttons.increment_clicks(button_id)
        # Off the hot path (D-052): the per-event ad_events row is fire-and-forget;
        # the advertisements/ad_buttons click counters above stay authoritative.
        if self._events is not None:
            self._events.record_click(
                advertisement_id=ad_id, user_id=user_row_id, button_id=button_id
            )
        if button_id is not None:
            button = await self._buttons.get_by_id(button_id)
            _log.info("ad_click", ad_id=ad_id, button_id=button_id)
            if button is not None and button.url:
                return str(button.url)
        else:
            _log.info("ad_click", ad_id=ad_id)
        return str(ad.button_url) if ad.button_url else None

    async def preview(self, ad_id: int, chat_id: int) -> bool:
        """Render an ad to the Owner exactly as a user would see it (/ad_preview)."""
        ad = await self._ads.get_by_id(ad_id)
        if ad is None:
            return False
        await self._deliver(ad, chat_id)
        return True

    async def prepare_broadcast(self, ad_id: int) -> AdBroadcastPlan | None:
        """Resolve an ad into a reusable delivery plan for a broadcast (Sprint 9.5)."""
        ad = await self._ads.get_by_id(ad_id)
        if ad is None:
            return None
        buttons = await self._build_buttons(ad)
        return AdBroadcastPlan(
            delivery_mode=ad.delivery_mode,
            ad_type=ad.type,
            content_text=ad.content_text,
            content_media_file_id=ad.content_media_file_id,
            parse_mode=ad.parse_mode,
            storage_chat_id=ad.storage_chat_id,
            storage_message_id=ad.storage_message_id,
            buttons=tuple(buttons),
        )

    # --- ad CRUD (Tasks 9.2 + 9.5) ---------------------------------------
    async def create(
        self,
        fields: Mapping[str, str],
        *,
        created_by: int,
        media_file_id: str | None = None,
        default_frequency: int = 1,
        storage_chat_id: int | None = None,
        storage_message_id: int | None = None,
    ) -> Any:
        """Validate ``fields`` (parsed ``key=value`` args) and insert an ad."""
        self._reject_unknown(fields)
        title = (fields.get("title") or "").strip()
        if not title:
            raise InvalidAdError("An ad needs a title (title=...).")
        ad_type = _parse_type(fields.get("type"))
        placement = _parse_choice(
            fields.get("placement"), AdPlacement, "placement", default="post_download"
        )
        delivery_mode = _parse_choice(
            fields.get("delivery"), AdDeliveryMode, "delivery", default="fields"
        )
        audience_mode = _parse_choice(
            fields.get("audience"), AudienceMode, "audience", default="all"
        )
        parse_mode = _clean(fields.get("parse_mode"))
        content_text = _clean(fields.get("text"))
        content_media_file_id = media_file_id or _clean(fields.get("file_id"))
        button_text, button_url = _parse_button(fields.get("button_text"), fields.get("button_url"))
        target_role = _parse_target(fields.get("target"))
        every = _coerce_int(fields.get("every"), "every", default=default_frequency, minimum=1)
        priority = _coerce_int(fields.get("priority"), "priority", default=0)
        store_chat = storage_chat_id or _coerce_opt_int(
            fields.get("storage_chat_id"), "storage_chat_id"
        )
        store_msg = storage_message_id or _coerce_opt_int(
            fields.get("storage_message_id"), "storage_message_id"
        )
        scheduled_at = _parse_schedule(fields.get("scheduled_at"))
        internal_name = _clean(fields.get("internal_name"))
        internal_notes = _clean(fields.get("notes"))
        target_language = _clean(fields.get("language"))

        if delivery_mode == AdDeliveryMode.COPY.value:
            if store_chat is None or store_msg is None:
                raise InvalidAdError(
                    "A copy-mode ad needs storage_chat_id + storage_message_id "
                    "(reply to the stored message, or pass them)."
                )
        else:
            _require_content(ad_type, content_text, content_media_file_id)

        return await self._ads.create_ad(
            title=title,
            ad_type=ad_type,
            content_text=content_text,
            content_media_file_id=content_media_file_id,
            button_text=button_text,
            button_url=button_url,
            target_role=target_role,
            show_every_n_downloads=every,
            priority=priority,
            created_by=created_by,
            placement=placement,
            delivery_mode=delivery_mode,
            storage_chat_id=store_chat,
            storage_message_id=store_msg,
            parse_mode=parse_mode,
            audience_mode=audience_mode,
            scheduled_at=scheduled_at,
            internal_name=internal_name,
            internal_notes=internal_notes,
            target_language=target_language,
        )

    async def list_ads(self) -> Sequence[Any]:
        return await self._ads.list_all_ads()

    async def get(self, ad_id: int) -> Any | None:
        return await self._ads.get_by_id(ad_id)

    async def edit(
        self, ad_id: int, fields: Mapping[str, str], *, media_file_id: str | None = None
    ) -> Any | None:
        ad = await self._ads.get_by_id(ad_id)
        if ad is None:
            return None
        changes = self._validate_edit(ad, fields, media_file_id)
        if not changes:
            raise InvalidAdError("Nothing to update — provide at least one field=value.")
        return await self._ads.apply_update(ad, changes)

    async def toggle(self, ad_id: int) -> tuple[Any, bool] | None:
        ad = await self._ads.get_by_id(ad_id)
        if ad is None:
            return None
        new_state = not ad.is_active
        updated = await self._ads.apply_update(ad, {"is_active": new_state})
        return updated, new_state

    async def set_active(self, ad_id: int, active: bool) -> Any | None:
        """Explicit enable/disable for ``/ad_enable`` and ``/ad_disable`` (9.5.8)."""
        ad = await self._ads.get_by_id(ad_id)
        if ad is None:
            return None
        return await self._ads.apply_update(ad, {"is_active": active})

    # --- placement-conflict detection (UX sprint #9) ---------------------
    async def targets_placement(self, ad_id: int, placement: str) -> bool:
        """Whether ``ad_id`` occupies ``placement`` (multi-placement rows, or legacy column)."""
        places = await self._ads.list_placements(ad_id)
        if places:
            return placement in places
        ad = await self._ads.get_by_id(ad_id)
        return ad is not None and ad.placement == placement

    async def active_conflicts(self, placement: str, *, exclude_id: int | None = None) -> list[Any]:
        """Other currently-active ads occupying ``placement`` (UX sprint #9).

        Used to warn an admin before a second ad goes live on a high-visibility placement
        (e.g. post-download): both may legitimately coexist and share exposure under the
        fair-rotation rule (#10), but the admin should choose that knowingly rather than
        create an unnoticed overlap. Excludes ``exclude_id`` (the ad being enabled/edited).
        """
        active = await self._ads.list_active_for_placement(placement)
        return [ad for ad in active if ad.id != exclude_id]

    async def replace_active_on_placement(self, placement: str, *, keep_id: int) -> list[int]:
        """Disable every active ad on ``placement`` except ``keep_id`` (the "Replace" choice).

        Returns the ids that were disabled, so the caller can report exactly what changed.
        """
        disabled: list[int] = []
        for ad in await self._ads.list_active_for_placement(placement):
            if ad.id != keep_id:
                await self._ads.apply_update(ad, {"is_active": False})
                disabled.append(ad.id)
        return disabled

    async def list_placements(self, ad_id: int) -> Sequence[str]:
        """The placements an ad occupies (Sprint 9.6, D-056)."""
        return await self._ads.list_placements(ad_id)

    async def set_placements(self, ad_id: int, placements: Sequence[str]) -> list[str] | None:
        """Replace an ad's placement set (Sprint 9.6, D-056); None if no such ad.

        Each value is validated against :class:`AdPlacement`; an ad must keep at least one
        placement. Per-placement §13.6 toggles still gate whether it actually shows.
        """
        if await self._ads.get_by_id(ad_id) is None:
            return None
        valid = {p.value for p in AdPlacement}
        cleaned: list[str] = []
        for placement in placements:
            token = placement.strip().lower()
            if token not in valid:
                opts = ", ".join(sorted(valid))
                raise InvalidAdError(f"Unknown placement {placement!r}. Use one of: {opts}.")
            cleaned.append(token)
        deduped = list(dict.fromkeys(cleaned))  # drop duplicates, preserve order
        if not deduped:
            raise InvalidAdError("An ad needs at least one placement.")
        await self._ads.set_placements(ad_id, deduped)
        return deduped

    async def delete(self, ad_id: int) -> bool:
        ad = await self._ads.get_by_id(ad_id)
        if ad is None:
            return False
        await self._ads.delete(ad)
        return True

    async def overall_stats(self) -> AdStats:
        ads = await self._ads.list_all_ads()
        return AdStats(
            total_ads=len(ads),
            active_ads=sum(1 for ad in ads if ad.is_active),
            impressions=sum(ad.impressions for ad in ads),
            clicks=sum(ad.clicks for ad in ads),
        )

    async def set_global(self, enabled: bool, *, updated_by: int) -> None:
        await self._settings.set_validated(
            "ads_enabled", "true" if enabled else "false", updated_by=updated_by
        )

    # --- multi-button management (Task 9.5.2) ----------------------------
    async def add_button(
        self, ad_id: int, *, text: str, url: str, row: int = 0, position: int = 0
    ) -> Any | None:
        if await self._ads.get_by_id(ad_id) is None:
            return None
        if not text.strip() or not url.strip():
            raise InvalidAdError("A button needs both text and url.")
        return await self._buttons.create_button(
            advertisement_id=ad_id, text=text.strip(), url=url.strip(), row=row, position=position
        )

    async def clear_buttons(self, ad_id: int) -> int:
        return await self._buttons.delete_for_ad(ad_id)

    async def list_buttons(self, ad_id: int) -> Sequence[Any]:
        return await self._buttons.list_for_ad(ad_id)

    # --- helpers ---------------------------------------------------------
    def _reject_unknown(self, fields: Mapping[str, str]) -> None:
        unknown = set(fields) - _EDITABLE_FIELDS
        if unknown:
            raise InvalidAdError(f"Unknown field(s): {', '.join(sorted(unknown))}")

    def _validate_edit(
        self, ad: Any, fields: Mapping[str, str], media_file_id: str | None
    ) -> dict[str, Any]:
        self._reject_unknown(fields)
        changes: dict[str, Any] = {}
        if "title" in fields:
            title = fields["title"].strip()
            if not title:
                raise InvalidAdError("Title must not be empty.")
            changes["title"] = title
        if "type" in fields:
            changes["type"] = _parse_type(fields["type"])
        if "text" in fields:
            changes["content_text"] = _clean(fields["text"])
        if media_file_id is not None or "file_id" in fields:
            changes["content_media_file_id"] = media_file_id or _clean(fields.get("file_id"))
        if "button_text" in fields or "button_url" in fields:
            new_text = fields["button_text"] if "button_text" in fields else ad.button_text
            new_url = fields["button_url"] if "button_url" in fields else ad.button_url
            button_text, button_url = _parse_button(new_text, new_url)
            changes["button_text"] = button_text
            changes["button_url"] = button_url
        if "target" in fields:
            changes["target_role"] = _parse_target(fields["target"])
        if "every" in fields:
            changes["show_every_n_downloads"] = _coerce_int(fields["every"], "every", minimum=1)
        if "priority" in fields:
            changes["priority"] = _coerce_int(fields["priority"], "priority")
        if "placement" in fields:
            changes["placement"] = _parse_choice(fields["placement"], AdPlacement, "placement")
        if "delivery" in fields:
            changes["delivery_mode"] = _parse_choice(fields["delivery"], AdDeliveryMode, "delivery")
        if "audience" in fields:
            changes["audience_mode"] = _parse_choice(fields["audience"], AudienceMode, "audience")
        if "parse_mode" in fields:
            changes["parse_mode"] = _clean(fields["parse_mode"])
        if "storage_chat_id" in fields:
            changes["storage_chat_id"] = _coerce_opt_int(
                fields["storage_chat_id"], "storage_chat_id"
            )
        if "storage_message_id" in fields:
            changes["storage_message_id"] = _coerce_opt_int(
                fields["storage_message_id"], "storage_message_id"
            )
        if "scheduled_at" in fields:
            changes["scheduled_at"] = _parse_schedule(fields["scheduled_at"])
        if "internal_name" in fields:
            changes["internal_name"] = _clean(fields["internal_name"])
        if "notes" in fields:
            changes["internal_notes"] = _clean(fields["notes"])
        if "language" in fields:
            changes["target_language"] = _clean(fields["language"])

        final_mode = changes.get("delivery_mode", ad.delivery_mode)
        if final_mode != AdDeliveryMode.COPY.value:
            final_type = changes.get("type", ad.type)
            final_text = changes.get("content_text", ad.content_text)
            final_media = changes.get("content_media_file_id", ad.content_media_file_id)
            _require_content(final_type, final_text, final_media)
        return changes


def _is_premium_active(is_premium: bool, premium_expires_at: datetime.datetime | None) -> bool:
    """``True`` while an unexpired premium grant is active (mirrors 16.5 plan logic)."""
    return (
        bool(is_premium)
        and premium_expires_at is not None
        and premium_expires_at > datetime.datetime.now(datetime.UTC)
    )


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _parse_type(value: str | None) -> str:
    raw = (value or AdType.TEXT.value).strip().lower()
    try:
        return AdType(raw).value
    except ValueError as exc:
        valid = ", ".join(t.value for t in AdType)
        raise InvalidAdError(f"Unknown ad type {raw!r}. Use one of: {valid}.") from exc


def _parse_choice(
    value: str | None, enum: type[Any], field: str, *, default: str | None = None
) -> str:
    if value is None or not value.strip():
        if default is None:
            raise InvalidAdError(f"{field} is required.")
        return default
    raw = value.strip().lower()
    try:
        return str(enum(raw).value)
    except ValueError as exc:
        valid = ", ".join(m.value for m in enum)
        raise InvalidAdError(f"Unknown {field} {raw!r}. Use one of: {valid}.") from exc


def _parse_target(value: str | None) -> str | None:
    if value is None:
        return None
    token = value.strip().lower()
    if token in _UNTARGETED_TOKENS:
        return None
    if token not in _AD_TARGET_ROLES:
        valid = ", ".join(sorted(_AD_TARGET_ROLES))
        raise InvalidAdError(f"target must be one of: {valid}, or none.")
    return token


def _parse_button(text: str | None, url: str | None) -> tuple[str | None, str | None]:
    button_text = _clean(text)
    button_url = _clean(url)
    if (button_text is None) != (button_url is None):
        raise InvalidAdError("A button needs both button_text and button_url (or neither).")
    return button_text, button_url


def _coerce_int(
    value: str | None, field: str, *, default: int | None = None, minimum: int | None = None
) -> int:
    if value is None or not value.strip():
        if default is None:
            raise InvalidAdError(f"{field} is required and must be an integer.")
        return default
    try:
        parsed = int(value.strip())
    except ValueError as exc:
        raise InvalidAdError(f"{field} must be an integer, got {value!r}.") from exc
    if minimum is not None and parsed < minimum:
        raise InvalidAdError(f"{field} must be >= {minimum}.")
    return parsed


def _parse_schedule(value: str | None) -> datetime.datetime | None:
    """Parse a ``scheduled_at`` field to a UTC datetime; ``none``/empty clears it (9.5.10)."""
    if value is None:
        return None
    if value.strip().lower() in _CLEAR_TOKENS:
        return None
    try:
        return parse_iso_datetime(value)
    except ValueError as exc:
        raise InvalidAdError(
            f"scheduled_at must be an ISO-8601 timestamp (e.g. 2026-07-01T12:00:00Z), "
            f"got {value!r}."
        ) from exc


def _coerce_opt_int(value: str | None, field: str) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        return int(value.strip())
    except ValueError as exc:
        raise InvalidAdError(f"{field} must be an integer, got {value!r}.") from exc


def _require_content(
    ad_type: str, content_text: str | None, content_media_file_id: str | None
) -> None:
    if ad_type == AdType.TEXT.value:
        if not content_text:
            raise InvalidAdError("A text ad needs text=... content.")
    elif ad_type == AdType.ALBUM.value:
        raise InvalidAdError("Album ads must use copy mode (delivery=copy).")
    elif not content_media_file_id:
        raise InvalidAdError(
            f"A {ad_type} ad needs a media file_id (attach the media or pass file_id=...)."
        )
