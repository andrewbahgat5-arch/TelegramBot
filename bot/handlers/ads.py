"""Ad handlers (MASTER_PLAN Sprint 9, Tasks 9.2 + 9.4; Sprint 11.5 i18n).

Two surfaces share this router:

* **Owner-only admin commands** — ``/ad_create``, ``/ad_list``, ``/ad_edit``,
  ``/ad_toggle``, ``/ad_delete``, ``/ad_stats``, ``/ad_global``. Authorization is the
  declarative ``OwnerFilter`` (Section 9.1: handlers never decide authz); a non-owner
  matches no handler and is **silently ignored** (item #18), consistent with the other
  admin commands. No business logic lives here — parse, delegate to ``AdService``,
  format (Section 9.1).
* **The public ad-click callback** (``a|<ad_id>``, Task 9.4 / flow 16.7 W6) — any user
  who taps an ad button. It records the click and delivers the destination link
  (Telegram URL buttons fire no callback, so the button is a callback button and the
  handler hands the user the link).

Per-request services arrive as aiogram workflow data (``ad_service_factory``,
``callback_signer``). Chrome (usage hints, confirmations, errors) is localized; ad
titles/content and broadcast bodies are user/owner-authored content and are never
translated (Sprint 11.5 requirement #3).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.callbacks.factory import CallbackSigner
from bot.filters.role_filter import RoleFilter
from core.i18n import Translator
from core.logging import get_logger
from core.timeparse import parse_iso_datetime
from domain.entities.user import UserSnapshot
from domain.enums import AudienceDimension, AudienceEffect, AudienceMode, UserRole
from services.ad_service import AdService, AdStats, InvalidAdError
from services.audience_service import AudienceService
from services.broadcast_service import BroadcastService, InvalidBroadcastError
from services.user_service import UserService

router = Router(name="ads")
_log = get_logger("bot.handlers.ads")

AdServiceFactory = Callable[[AsyncSession], AdService]
AudienceServiceFactory = Callable[[AsyncSession], AudienceService]
BroadcastServiceFactory = Callable[[AsyncSession], BroadcastService]
UserServiceFactory = Callable[[AsyncSession], UserService]

OwnerFilter = RoleFilter(UserRole.OWNER)

# /ad_audience dimension aliases → AudienceDimension values.
_DIMENSION_ALIASES = {
    "role": AudienceDimension.ROLE.value,
    "plan": AudienceDimension.PLAN.value,
    "lang": AudienceDimension.LANGUAGE.value,
    "language": AudienceDimension.LANGUAGE.value,
    "user": AudienceDimension.USER_ID.value,
    "user_id": AudienceDimension.USER_ID.value,
    "segment": AudienceDimension.SEGMENT.value,
    "country": AudienceDimension.COUNTRY.value,
}


async def show_placement_ad(service: AdService, user: UserSnapshot, placement: str) -> None:
    """Best-effort: deliver an ad at a persistent placement (Sprint 9.5). Never raises.

    Gated by the per-placement ``settings`` toggle inside ``maybe_show`` (new placements
    default off), so it is a no-op unless the Owner has enabled that surface.
    """
    try:
        await service.maybe_show(
            chat_id=user.telegram_id,
            role=user.role.value,
            is_premium=user.is_premium,
            premium_expires_at=user.premium_expires_at,
            total_downloads=user.total_downloads,
            language=user.language,
            telegram_id=user.telegram_id,
            user_row_id=user.id,
            placement=placement,
        )
    except Exception as exc:  # a placement ad must never break the surface it rides on
        _log.warning("placement_ad_failed", placement=placement, error=str(exc))


_FIELD_RE = re.compile(r"^([a-z_]+)=(.*)$")


# --- /ad_create -----------------------------------------------------------
@router.message(Command("ad_create"), OwnerFilter)
async def handle_ad_create(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    user: UserSnapshot,
    ad_service_factory: AdServiceFactory,
    translate: Translator,
    locale: str,
) -> None:
    fields = _parse_fields(command.args)
    if not fields:
        await message.answer(translate("ads.create.usage", locale))
        return
    storage_chat_id, storage_message_id = _reply_storage(message)
    try:
        ad = await ad_service_factory(session).create(
            fields,
            created_by=user.id,
            media_file_id=_attached_media_file_id(message),
            storage_chat_id=storage_chat_id,
            storage_message_id=storage_message_id,
        )
    except InvalidAdError as exc:
        await message.answer(translate("ads.create.failed", locale, error=escape(str(exc))))
        return
    await message.answer(translate("ads.create.success", locale, id=ad.id, title=escape(ad.title)))


# --- /ad_list -------------------------------------------------------------
@router.message(Command("ad_list"), OwnerFilter)
async def handle_ad_list(
    message: Message,
    session: AsyncSession,
    ad_service_factory: AdServiceFactory,
    translate: Translator,
    locale: str,
) -> None:
    ads = await ad_service_factory(session).list_ads()
    if not ads:
        await message.answer(translate("ads.list.empty", locale))
        return
    lines = [translate("ads.list.header", locale)]
    lines += [_format_ad_row(ad, translate, locale) for ad in ads]
    await message.answer("\n".join(lines))


# --- /ad_edit -------------------------------------------------------------
@router.message(Command("ad_edit"), OwnerFilter)
async def handle_ad_edit(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    ad_service_factory: AdServiceFactory,
    translate: Translator,
    locale: str,
) -> None:
    ad_id, rest = _split_id(command.args)
    if ad_id is None:
        await message.answer(translate("ads.edit.usage", locale))
        return
    fields = _parse_fields(rest)
    try:
        ad = await ad_service_factory(session).edit(
            ad_id, fields, media_file_id=_attached_media_file_id(message)
        )
    except InvalidAdError as exc:
        await message.answer(translate("ads.edit.failed", locale, error=escape(str(exc))))
        return
    if ad is None:
        await message.answer(translate("ads.not_found", locale, id=ad_id))
        return
    await message.answer(translate("ads.edit.success", locale, id=ad_id))


# --- /ad_toggle -----------------------------------------------------------
@router.message(Command("ad_toggle"), OwnerFilter)
async def handle_ad_toggle(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    ad_service_factory: AdServiceFactory,
    translate: Translator,
    locale: str,
) -> None:
    ad_id, _ = _split_id(command.args)
    if ad_id is None:
        await message.answer(translate("ads.toggle.usage", locale))
        return
    result = await ad_service_factory(session).toggle(ad_id)
    if result is None:
        await message.answer(translate("ads.not_found", locale, id=ad_id))
        return
    _, active = result
    state = translate("ads.state_enabled" if active else "ads.state_disabled", locale)
    await message.answer(translate("ads.toggle.result", locale, id=ad_id, state=state))


# --- /ad_delete -----------------------------------------------------------
@router.message(Command("ad_delete"), OwnerFilter)
async def handle_ad_delete(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    ad_service_factory: AdServiceFactory,
    translate: Translator,
    locale: str,
) -> None:
    ad_id, _ = _split_id(command.args)
    if ad_id is None:
        await message.answer(translate("ads.delete.usage", locale))
        return
    deleted = await ad_service_factory(session).delete(ad_id)
    if not deleted:
        await message.answer(translate("ads.not_found", locale, id=ad_id))
        return
    await message.answer(translate("ads.delete.success", locale, id=ad_id))


# --- /ad_stats ------------------------------------------------------------
@router.message(Command("ad_stats"), OwnerFilter)
async def handle_ad_stats(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    ad_service_factory: AdServiceFactory,
    translate: Translator,
    locale: str,
) -> None:
    service = ad_service_factory(session)
    ad_id, _ = _split_id(command.args)
    if ad_id is not None:
        ad = await service.get(ad_id)
        if ad is None:
            await message.answer(translate("ads.not_found", locale, id=ad_id))
            return
        await message.answer(_format_ad_stats(ad, translate, locale))
        return
    await message.answer(_format_overall_stats(await service.overall_stats(), translate, locale))


# --- /ad_global -----------------------------------------------------------
@router.message(Command("ad_global"), OwnerFilter)
async def handle_ad_global(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    user: UserSnapshot,
    ad_service_factory: AdServiceFactory,
    translate: Translator,
    locale: str,
) -> None:
    enabled = _parse_on_off(command.args)
    if enabled is None:
        await message.answer(translate("ads.global.usage", locale))
        return
    await ad_service_factory(session).set_global(enabled, updated_by=user.id)
    state = translate("ads.state_on" if enabled else "ads.state_off", locale)
    await message.answer(translate("ads.global.result", locale, state=state))


# --- /ad_enable + /ad_disable (Task 9.5.8) --------------------------------
@router.message(Command("ad_enable"), OwnerFilter)
async def handle_ad_enable(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    ad_service_factory: AdServiceFactory,
    translate: Translator,
    locale: str,
) -> None:
    await _set_active(message, command, ad_service_factory(session), translate, locale, active=True)


@router.message(Command("ad_disable"), OwnerFilter)
async def handle_ad_disable(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    ad_service_factory: AdServiceFactory,
    translate: Translator,
    locale: str,
) -> None:
    await _set_active(
        message, command, ad_service_factory(session), translate, locale, active=False
    )


async def _set_active(
    message: Message,
    command: CommandObject,
    service: AdService,
    translate: Translator,
    locale: str,
    *,
    active: bool,
) -> None:
    ad_id, _ = _split_id(command.args)
    if ad_id is None:
        verb = "ad_enable" if active else "ad_disable"
        await message.answer(translate("ads.enable_disable.usage", locale, verb=verb))
        return
    ad = await service.set_active(ad_id, active)
    if ad is None:
        await message.answer(translate("ads.not_found", locale, id=ad_id))
        return
    state = translate("ads.state_enabled" if active else "ads.state_disabled", locale)
    await message.answer(translate("ads.set_active.result", locale, id=ad_id, state=state))


# --- /ad_preview (Task 9.5.2) ---------------------------------------------
@router.message(Command("ad_preview"), OwnerFilter)
async def handle_ad_preview(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    ad_service_factory: AdServiceFactory,
    translate: Translator,
    locale: str,
) -> None:
    ad_id, _ = _split_id(command.args)
    if ad_id is None:
        await message.answer(translate("ads.preview.usage", locale))
        return
    shown = await ad_service_factory(session).preview(ad_id, message.chat.id)
    if not shown:
        await message.answer(translate("ads.not_found", locale, id=ad_id))


# --- /ad_button_add + /ad_button_clear (Task 9.5.2) -----------------------
@router.message(Command("ad_button_add"), OwnerFilter)
async def handle_ad_button_add(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    ad_service_factory: AdServiceFactory,
    translate: Translator,
    locale: str,
) -> None:
    ad_id, rest = _split_id(command.args)
    text, url, row = _parse_button_spec(rest)
    if ad_id is None or text is None or url is None:
        await message.answer(translate("ads.button_add.usage", locale))
        return
    try:
        button = await ad_service_factory(session).add_button(ad_id, text=text, url=url, row=row)
    except InvalidAdError as exc:
        await message.answer(translate("ads.button_add.failed", locale, error=escape(str(exc))))
        return
    if button is None:
        await message.answer(translate("ads.not_found", locale, id=ad_id))
        return
    await message.answer(translate("ads.button_add.success", locale, id=ad_id))


@router.message(Command("ad_button_clear"), OwnerFilter)
async def handle_ad_button_clear(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    ad_service_factory: AdServiceFactory,
    translate: Translator,
    locale: str,
) -> None:
    ad_id, _ = _split_id(command.args)
    if ad_id is None:
        await message.answer(translate("ads.button_clear.usage", locale))
        return
    removed = await ad_service_factory(session).clear_buttons(ad_id)
    await message.answer(translate("ads.button_clear.success", locale, count=removed, id=ad_id))


# --- /ad_audience (Task 9.5.5) --------------------------------------------
@router.message(Command("ad_audience"), OwnerFilter)
async def handle_ad_audience(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    ad_service_factory: AdServiceFactory,
    audience_service_factory: AudienceServiceFactory,
    translate: Translator,
    locale: str,
) -> None:
    ad_id, rest = _split_id(command.args)
    if ad_id is None:
        await message.answer(translate("ads.audience.usage", locale))
        return
    try:
        mode, rules = _parse_audience_args(rest, translate, locale)
    except ValueError as exc:
        await message.answer(translate("ads.audience.invalid", locale, error=str(exc)))
        return
    ad_service = ad_service_factory(session)
    if await ad_service.edit(ad_id, {"audience": mode}) is None:
        await message.answer(translate("ads.not_found", locale, id=ad_id))
        return
    audience = audience_service_factory(session)
    await audience.clear_rules(ad_id)
    for effect, dimension, value in rules:
        await audience.add_rule(ad_id, effect=effect, dimension=dimension, value=value)
    await message.answer(
        translate("ads.audience.success", locale, id=ad_id, mode=mode, count=len(rules))
    )


# --- /ad_broadcast (Task 9.5.7) -------------------------------------------
@router.message(Command("ad_broadcast"), OwnerFilter)
async def handle_ad_broadcast(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    user: UserSnapshot,
    ad_service_factory: AdServiceFactory,
    broadcast_service_factory: BroadcastServiceFactory,
    translate: Translator,
    locale: str,
) -> None:
    ad_id, rest = _split_id(command.args)
    if ad_id is None:
        await message.answer(translate("ads.broadcast.usage", locale))
        return
    if await ad_service_factory(session).get(ad_id) is None:
        await message.answer(translate("ads.not_found", locale, id=ad_id))
        return
    language, role, at_raw = _parse_target_flags(rest)
    scheduled_at = None
    if at_raw is not None:
        try:
            scheduled_at = parse_iso_datetime(at_raw)
        except ValueError:
            await message.answer(translate("admin.broadcast.invalid_at", locale))
            return
    try:
        broadcast = await broadcast_service_factory(session).create_from_ad(
            created_by_user_id=user.id,
            advertisement_id=ad_id,
            target_language=language,
            target_role=role,
            scheduled_at=scheduled_at,
        )
    except InvalidBroadcastError as exc:
        await message.answer(translate("admin.broadcast.failed", locale, error=escape(str(exc))))
        return
    target = _describe_target(language, role, translate, locale)
    when = (
        translate("admin.broadcast.scheduled_suffix", locale, when=f"{scheduled_at:%Y-%m-%d %H:%M}")
        if scheduled_at
        else ""
    )
    await message.answer(
        translate(
            "ads.broadcast.queued",
            locale,
            id=ad_id,
            broadcast_id=broadcast.id,
            count=broadcast.expected_total,
            target=target,
            when=when,
        )
    )


# --- /ad_segment_* (Task 9.5.5) -------------------------------------------
@router.message(Command("ad_segment_create"), OwnerFilter)
async def handle_ad_segment_create(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    user: UserSnapshot,
    audience_service_factory: AudienceServiceFactory,
    translate: Translator,
    locale: str,
) -> None:
    name, description = _parse_name_and_rest(command.args)
    if not name:
        await message.answer(translate("ads.segment.create.usage", locale))
        return
    audience = audience_service_factory(session)
    if await audience.find_segment(name) is not None:
        await message.answer(translate("ads.segment.exists", locale, name=escape(name)))
        return
    segment = await audience.create_segment(name=name, description=description, created_by=user.id)
    await message.answer(translate("ads.segment.created", locale, id=segment.id, name=escape(name)))


@router.message(Command("ad_segment_add"), OwnerFilter)
async def handle_ad_segment_add(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    audience_service_factory: AudienceServiceFactory,
    user_service_factory: UserServiceFactory,
    translate: Translator,
    locale: str,
) -> None:
    await _segment_membership(
        message,
        command,
        audience_service_factory(session),
        user_service_factory(session),
        translate,
        locale,
        add=True,
    )


@router.message(Command("ad_segment_remove"), OwnerFilter)
async def handle_ad_segment_remove(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    audience_service_factory: AudienceServiceFactory,
    user_service_factory: UserServiceFactory,
    translate: Translator,
    locale: str,
) -> None:
    await _segment_membership(
        message,
        command,
        audience_service_factory(session),
        user_service_factory(session),
        translate,
        locale,
        add=False,
    )


@router.message(Command("ad_segment_list"), OwnerFilter)
async def handle_ad_segment_list(
    message: Message,
    session: AsyncSession,
    audience_service_factory: AudienceServiceFactory,
    translate: Translator,
    locale: str,
) -> None:
    audience = audience_service_factory(session)
    segments = await audience.list_segments()
    if not segments:
        await message.answer(translate("ads.segment.list.empty", locale))
        return
    lines = [translate("ads.segment.list.header", locale)]
    for seg in segments:
        count = await audience.count_members(seg.id)
        lines.append(
            translate("ads.segment.list.row", locale, id=seg.id, name=escape(seg.name), count=count)
        )
    await message.answer("\n".join(lines))


async def _segment_membership(
    message: Message,
    command: CommandObject,
    audience: AudienceService,
    users: UserService,
    translate: Translator,
    locale: str,
    *,
    add: bool,
) -> None:
    name, telegram_id = _parse_name_and_id(command.args)
    if name is None or telegram_id is None:
        verb = "ad_segment_add" if add else "ad_segment_remove"
        await message.answer(translate("ads.segment.membership.usage", locale, verb=verb))
        return
    segment = await audience.find_segment(name)
    if segment is None:
        await message.answer(translate("ads.segment.not_found", locale, name=escape(name)))
        return
    snap = await users.find(telegram_id)
    if snap is None:
        await message.answer(translate("admin.userinfo.not_found", locale, id=telegram_id))
        return
    if add:
        await audience.add_member(segment_id=segment.id, user_row_id=snap.id)
        await message.answer(
            translate("ads.segment.added", locale, id=telegram_id, name=escape(name))
        )
    else:
        await audience.remove_member(segment_id=segment.id, user_row_id=snap.id)
        await message.answer(
            translate("ads.segment.removed", locale, id=telegram_id, name=escape(name))
        )


# --- ad-click callback (Task 9.4, flow 16.7 W6) ---------------------------
@router.callback_query(F.data.startswith("a|"))
async def handle_ad_click(
    callback: CallbackQuery,
    session: AsyncSession,
    user: UserSnapshot,
    ad_service_factory: AdServiceFactory,
    callback_signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> None:
    parsed = callback_signer.unpack(callback.data or "")
    if parsed is None or parsed.action != "a" or parsed.arg is None:
        await callback.answer()  # forged/garbled → ignore silently (Section 14.2)
        return
    await callback.answer()
    url = await ad_service_factory(session).record_click(
        parsed.arg, parsed.button_id, user_row_id=user.id
    )
    if url and isinstance(callback.message, Message):
        await callback.message.answer(translate("ads.click.open_link", locale, url=escape(url)))


# --- parsing helpers ------------------------------------------------------
def _parse_fields(raw: str | None) -> dict[str, str]:
    """Parse ``key=value`` tokens; a value runs until the next ``key=`` token.

    Lets a value contain spaces (``text=Big sale today button_text=Shop``). Tokens
    before the first ``key=`` are ignored (e.g. a leading id, handled separately).
    """
    fields: dict[str, str] = {}
    if not raw:
        return fields
    current: str | None = None
    parts: list[str] = []
    for token in raw.split():
        match = _FIELD_RE.match(token)
        if match:
            if current is not None:
                fields[current] = " ".join(parts).strip()
            current = match.group(1)
            parts = [match.group(2)]
        elif current is not None:
            parts.append(token)
    if current is not None:
        fields[current] = " ".join(parts).strip()
    return fields


def _split_id(raw: str | None) -> tuple[int | None, str | None]:
    if not raw:
        return None, None
    parts = raw.strip().split(maxsplit=1)
    try:
        ad_id = int(parts[0])
    except (ValueError, IndexError):
        return None, None
    rest = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
    return ad_id, rest


def _reply_storage(message: Message) -> tuple[int | None, int | None]:
    """Capture (chat_id, message_id) of a replied-to message for copy-mode ads."""
    reply = message.reply_to_message
    if reply is None:
        return None, None
    return reply.chat.id, reply.message_id


def _parse_button_spec(raw: str | None) -> tuple[str | None, str | None, int]:
    """Parse ``<text> | <url> [| row]`` for ``/ad_button_add``."""
    if not raw:
        return None, None, 0
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None, None, 0
    row = 0
    if len(parts) > 2 and parts[2].isdigit():
        row = int(parts[2])
    return parts[0], parts[1], row


def _parse_audience_args(
    raw: str | None, translate: Translator, locale: str
) -> tuple[str, list[tuple[str, str, str]]]:
    """Parse ``<mode> [!]dim:value …`` → (audience_mode, [(effect, dimension, value)]).

    A ``!`` prefix marks an exclude rule; otherwise the rule is an include rule. Raises
    ``ValueError`` on an unknown mode or dimension.
    """
    tokens = (raw or "").split()
    if not tokens:
        raise ValueError(translate("ads.audience.error_need_mode", locale))
    mode = tokens[0].lower()
    if mode not in (m.value for m in AudienceMode):
        modes = ", ".join(m.value for m in AudienceMode)
        raise ValueError(translate("ads.audience.error_bad_mode", locale, modes=modes))
    rules: list[tuple[str, str, str]] = []
    for token in tokens[1:]:
        effect = AudienceEffect.INCLUDE.value
        body = token
        if body.startswith("!"):
            effect = AudienceEffect.EXCLUDE.value
            body = body[1:]
        if ":" not in body:
            raise ValueError(translate("ads.audience.error_bad_rule", locale, rule=token))
        dim_raw, value = body.split(":", 1)
        dimension = _DIMENSION_ALIASES.get(dim_raw.lower())
        if dimension is None:
            raise ValueError(translate("ads.audience.error_bad_dimension", locale, dim=dim_raw))
        if not value:
            raise ValueError(translate("ads.audience.error_need_value", locale, rule=token))
        rules.append((effect, dimension, value))
    return mode, rules


def _parse_target_flags(raw: str | None) -> tuple[str | None, str | None, str | None]:
    """Parse ``[--lang xx] [--role xx] [--at <iso>]`` → (language, role, at)."""
    language: str | None = None
    role: str | None = None
    at_raw: str | None = None
    tokens = (raw or "").split()
    index = 0
    while index < len(tokens):
        if tokens[index] == "--lang" and index + 1 < len(tokens):
            language = tokens[index + 1]
            index += 2
        elif tokens[index] == "--role" and index + 1 < len(tokens):
            role = tokens[index + 1]
            index += 2
        elif tokens[index] == "--at" and index + 1 < len(tokens):
            at_raw = tokens[index + 1]
            index += 2
        else:
            index += 1
    return language, role, at_raw


def _parse_name_and_id(raw: str | None) -> tuple[str | None, int | None]:
    if not raw:
        return None, None
    parts = raw.strip().split()
    if len(parts) < 2:
        return None, None
    try:
        return parts[0], int(parts[1])
    except ValueError:
        return None, None


def _parse_name_and_rest(raw: str | None) -> tuple[str | None, str | None]:
    if not raw:
        return None, None
    parts = raw.strip().split(maxsplit=1)
    name = parts[0] if parts and parts[0] else None
    rest = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
    return name, rest


def _describe_target(
    language: str | None, role: str | None, translate: Translator, locale: str
) -> str:
    parts = []
    if role is not None:
        parts.append(translate("admin.broadcast.target_role_part", locale, role=role))
    if language is not None:
        parts.append(translate("admin.broadcast.target_lang_part", locale, language=language))
    return f" ({', '.join(parts)})" if parts else ""


def _parse_on_off(raw: str | None) -> bool | None:
    if not raw:
        return None
    token = raw.strip().lower()
    if token in ("on", "true", "1", "yes", "enable", "enabled"):
        return True
    if token in ("off", "false", "0", "no", "disable", "disabled"):
        return False
    return None


def _attached_media_file_id(message: Message) -> str | None:
    """Extract a media ``file_id`` from the command message or the message it replies to."""
    for source in (message, message.reply_to_message):
        if source is None:
            continue
        if source.photo:
            return source.photo[-1].file_id
        if source.video is not None:
            return source.video.file_id
        if source.animation is not None:
            return source.animation.file_id
    return None


# --- formatting helpers ---------------------------------------------------
def _format_ad_row(ad: Any, translate: Translator, locale: str) -> str:
    state = "✅" if ad.is_active else "⏸"
    target = ad.target_role or translate("panel.ads.target_all", locale)
    return translate(
        "ads.row.format",
        locale,
        state=state,
        id=ad.id,
        title=escape(ad.title),
        type=ad.type,
        priority=ad.priority,
        frequency=ad.show_every_n_downloads,
        target=target,
        impressions=ad.impressions,
        clicks=ad.clicks,
    )


def _format_ad_stats(ad: Any, translate: Translator, locale: str) -> str:
    return translate(
        "ads.stats.row",
        locale,
        id=ad.id,
        title=escape(ad.title),
        impressions=ad.impressions,
        clicks=ad.clicks,
        ctr=_ctr(ad.impressions, ad.clicks),
    )


def _format_overall_stats(stats: AdStats, translate: Translator, locale: str) -> str:
    return translate(
        "ads.stats.overall",
        locale,
        total=stats.total_ads,
        active=stats.active_ads,
        impressions=stats.impressions,
        clicks=stats.clicks,
        ctr=_ctr(stats.impressions, stats.clicks),
    )


def _ctr(impressions: int, clicks: int) -> str:
    if impressions <= 0:
        return "—"
    return f"{clicks / impressions * 100:.1f}%"
