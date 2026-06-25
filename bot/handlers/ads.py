"""Ad handlers (MASTER_PLAN Sprint 9, Tasks 9.2 + 9.4).

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
``callback_signer``).
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
from core.logging import get_logger
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
_CREATE_USAGE = (
    "Usage: <code>/ad_create title=... type=text text=...</code>\n"
    "Fields: title, type (text/photo/video/animation/document/audio/album), text, "
    "file_id, button_text, button_url, target (user/premium/none), every, priority, "
    "placement, delivery (fields/copy), audience (all/include/exclude), parse_mode.\n"
    "For media ads, attach the media or reply to it. For a rich copy-mode ad, set "
    "<code>delivery=copy</code> and reply to the stored message.\n"
    "More buttons: <code>/ad_button_add</code>. Targeting: <code>/ad_audience</code>."
)


# --- /ad_create -----------------------------------------------------------
@router.message(Command("ad_create"), OwnerFilter)
async def handle_ad_create(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    user: UserSnapshot,
    ad_service_factory: AdServiceFactory,
) -> None:
    fields = _parse_fields(command.args)
    if not fields:
        await message.answer(_CREATE_USAGE)
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
        await message.answer(f"Cannot create ad: {escape(str(exc))}")
        return
    await message.answer(f"✅ Created ad #{ad.id} — <b>{escape(ad.title)}</b>.")


# --- /ad_list -------------------------------------------------------------
@router.message(Command("ad_list"), OwnerFilter)
async def handle_ad_list(
    message: Message,
    session: AsyncSession,
    ad_service_factory: AdServiceFactory,
) -> None:
    ads = await ad_service_factory(session).list_ads()
    if not ads:
        await message.answer("No ads configured yet. Create one with <code>/ad_create</code>.")
        return
    lines = ["📣 <b>Advertisements</b>"]
    lines += [_format_ad_row(ad) for ad in ads]
    await message.answer("\n".join(lines))


# --- /ad_edit -------------------------------------------------------------
@router.message(Command("ad_edit"), OwnerFilter)
async def handle_ad_edit(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    ad_service_factory: AdServiceFactory,
) -> None:
    ad_id, rest = _split_id(command.args)
    if ad_id is None:
        await message.answer("Usage: <code>/ad_edit &lt;id&gt; field=value ...</code>")
        return
    fields = _parse_fields(rest)
    try:
        ad = await ad_service_factory(session).edit(
            ad_id, fields, media_file_id=_attached_media_file_id(message)
        )
    except InvalidAdError as exc:
        await message.answer(f"Cannot edit ad: {escape(str(exc))}")
        return
    if ad is None:
        await message.answer(f"No ad with id <code>{ad_id}</code>.")
        return
    await message.answer(f"✅ Updated ad #{ad_id}.")


# --- /ad_toggle -----------------------------------------------------------
@router.message(Command("ad_toggle"), OwnerFilter)
async def handle_ad_toggle(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    ad_service_factory: AdServiceFactory,
) -> None:
    ad_id, _ = _split_id(command.args)
    if ad_id is None:
        await message.answer("Usage: <code>/ad_toggle &lt;id&gt;</code>")
        return
    result = await ad_service_factory(session).toggle(ad_id)
    if result is None:
        await message.answer(f"No ad with id <code>{ad_id}</code>.")
        return
    _, active = result
    state = "enabled ✅" if active else "disabled ⏸"
    await message.answer(f"Ad #{ad_id} {state}.")


# --- /ad_delete -----------------------------------------------------------
@router.message(Command("ad_delete"), OwnerFilter)
async def handle_ad_delete(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    ad_service_factory: AdServiceFactory,
) -> None:
    ad_id, _ = _split_id(command.args)
    if ad_id is None:
        await message.answer("Usage: <code>/ad_delete &lt;id&gt;</code>")
        return
    deleted = await ad_service_factory(session).delete(ad_id)
    if not deleted:
        await message.answer(f"No ad with id <code>{ad_id}</code>.")
        return
    await message.answer(f"🗑 Deleted ad #{ad_id}.")


# --- /ad_stats ------------------------------------------------------------
@router.message(Command("ad_stats"), OwnerFilter)
async def handle_ad_stats(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    ad_service_factory: AdServiceFactory,
) -> None:
    service = ad_service_factory(session)
    ad_id, _ = _split_id(command.args)
    if ad_id is not None:
        ad = await service.get(ad_id)
        if ad is None:
            await message.answer(f"No ad with id <code>{ad_id}</code>.")
            return
        await message.answer(_format_ad_stats(ad))
        return
    await message.answer(_format_overall_stats(await service.overall_stats()))


# --- /ad_global -----------------------------------------------------------
@router.message(Command("ad_global"), OwnerFilter)
async def handle_ad_global(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    user: UserSnapshot,
    ad_service_factory: AdServiceFactory,
) -> None:
    enabled = _parse_on_off(command.args)
    if enabled is None:
        await message.answer("Usage: <code>/ad_global &lt;on|off&gt;</code>")
        return
    await ad_service_factory(session).set_global(enabled, updated_by=user.id)
    state = "ON ✅" if enabled else "OFF ⏸"
    await message.answer(f"📣 Ads master switch is now <b>{state}</b>.")


# --- /ad_enable + /ad_disable (Task 9.5.8) --------------------------------
@router.message(Command("ad_enable"), OwnerFilter)
async def handle_ad_enable(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    ad_service_factory: AdServiceFactory,
) -> None:
    await _set_active(message, command, ad_service_factory(session), active=True)


@router.message(Command("ad_disable"), OwnerFilter)
async def handle_ad_disable(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    ad_service_factory: AdServiceFactory,
) -> None:
    await _set_active(message, command, ad_service_factory(session), active=False)


async def _set_active(
    message: Message, command: CommandObject, service: AdService, *, active: bool
) -> None:
    ad_id, _ = _split_id(command.args)
    if ad_id is None:
        verb = "ad_enable" if active else "ad_disable"
        await message.answer(f"Usage: <code>/{verb} &lt;id&gt;</code>")
        return
    ad = await service.set_active(ad_id, active)
    if ad is None:
        await message.answer(f"No ad with id <code>{ad_id}</code>.")
        return
    await message.answer(f"Ad #{ad_id} {'enabled ✅' if active else 'disabled ⏸'}.")


# --- /ad_preview (Task 9.5.2) ---------------------------------------------
@router.message(Command("ad_preview"), OwnerFilter)
async def handle_ad_preview(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    ad_service_factory: AdServiceFactory,
) -> None:
    ad_id, _ = _split_id(command.args)
    if ad_id is None:
        await message.answer("Usage: <code>/ad_preview &lt;id&gt;</code>")
        return
    shown = await ad_service_factory(session).preview(ad_id, message.chat.id)
    if not shown:
        await message.answer(f"No ad with id <code>{ad_id}</code>.")


# --- /ad_button_add + /ad_button_clear (Task 9.5.2) -----------------------
@router.message(Command("ad_button_add"), OwnerFilter)
async def handle_ad_button_add(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    ad_service_factory: AdServiceFactory,
) -> None:
    ad_id, rest = _split_id(command.args)
    text, url, row = _parse_button_spec(rest)
    if ad_id is None or text is None or url is None:
        await message.answer(
            "Usage: <code>/ad_button_add &lt;id&gt; &lt;text&gt; | &lt;url&gt; [| row]</code>"
        )
        return
    try:
        button = await ad_service_factory(session).add_button(ad_id, text=text, url=url, row=row)
    except InvalidAdError as exc:
        await message.answer(f"Cannot add button: {escape(str(exc))}")
        return
    if button is None:
        await message.answer(f"No ad with id <code>{ad_id}</code>.")
        return
    await message.answer(f"✅ Added button to ad #{ad_id}.")


@router.message(Command("ad_button_clear"), OwnerFilter)
async def handle_ad_button_clear(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    ad_service_factory: AdServiceFactory,
) -> None:
    ad_id, _ = _split_id(command.args)
    if ad_id is None:
        await message.answer("Usage: <code>/ad_button_clear &lt;id&gt;</code>")
        return
    removed = await ad_service_factory(session).clear_buttons(ad_id)
    await message.answer(f"🗑 Removed {removed} button(s) from ad #{ad_id}.")


# --- /ad_audience (Task 9.5.5) --------------------------------------------
@router.message(Command("ad_audience"), OwnerFilter)
async def handle_ad_audience(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    ad_service_factory: AdServiceFactory,
    audience_service_factory: AudienceServiceFactory,
) -> None:
    ad_id, rest = _split_id(command.args)
    if ad_id is None:
        await message.answer(
            "Usage: <code>/ad_audience &lt;id&gt; &lt;all|include|exclude&gt; "
            "[!]dim:value …</code>\nDims: role, plan, lang, user, segment. "
            "Prefix <code>!</code> = exclude rule. Example: "
            "<code>/ad_audience 5 include plan:premium lang:ar</code>"
        )
        return
    try:
        mode, rules = _parse_audience_args(rest)
    except ValueError as exc:
        await message.answer(f"Invalid audience: {escape(str(exc))}")
        return
    ad_service = ad_service_factory(session)
    if await ad_service.edit(ad_id, {"audience": mode}) is None:
        await message.answer(f"No ad with id <code>{ad_id}</code>.")
        return
    audience = audience_service_factory(session)
    await audience.clear_rules(ad_id)
    for effect, dimension, value in rules:
        await audience.add_rule(ad_id, effect=effect, dimension=dimension, value=value)
    await message.answer(f"🎯 Ad #{ad_id} audience set to <b>{mode}</b> with {len(rules)} rule(s).")


# --- /ad_broadcast (Task 9.5.7) -------------------------------------------
@router.message(Command("ad_broadcast"), OwnerFilter)
async def handle_ad_broadcast(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    user: UserSnapshot,
    ad_service_factory: AdServiceFactory,
    broadcast_service_factory: BroadcastServiceFactory,
) -> None:
    ad_id, rest = _split_id(command.args)
    if ad_id is None:
        await message.answer("Usage: <code>/ad_broadcast &lt;id&gt; [--lang xx] [--role xx]</code>")
        return
    if await ad_service_factory(session).get(ad_id) is None:
        await message.answer(f"No ad with id <code>{ad_id}</code>.")
        return
    language, role = _parse_target_flags(rest)
    try:
        broadcast = await broadcast_service_factory(session).create_from_ad(
            created_by_user_id=user.id,
            advertisement_id=ad_id,
            target_language=language,
            target_role=role,
        )
    except InvalidBroadcastError as exc:
        await message.answer(f"Cannot broadcast: {escape(str(exc))}")
        return
    target = _describe_target(language, role)
    await message.answer(
        f"📢 Ad #{ad_id} broadcast #{broadcast.id} queued to "
        f"<b>{broadcast.expected_total}</b> users{target}."
    )


# --- /ad_segment_* (Task 9.5.5) -------------------------------------------
@router.message(Command("ad_segment_create"), OwnerFilter)
async def handle_ad_segment_create(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    user: UserSnapshot,
    audience_service_factory: AudienceServiceFactory,
) -> None:
    name, description = _parse_name_and_rest(command.args)
    if not name:
        await message.answer("Usage: <code>/ad_segment_create &lt;name&gt; [description]</code>")
        return
    audience = audience_service_factory(session)
    if await audience.find_segment(name) is not None:
        await message.answer(f"A segment named <code>{escape(name)}</code> already exists.")
        return
    segment = await audience.create_segment(name=name, description=description, created_by=user.id)
    await message.answer(f"✅ Created segment #{segment.id} <b>{escape(name)}</b>.")


@router.message(Command("ad_segment_add"), OwnerFilter)
async def handle_ad_segment_add(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    audience_service_factory: AudienceServiceFactory,
    user_service_factory: UserServiceFactory,
) -> None:
    await _segment_membership(
        message, command, audience_service_factory(session), user_service_factory(session), add=True
    )


@router.message(Command("ad_segment_remove"), OwnerFilter)
async def handle_ad_segment_remove(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    audience_service_factory: AudienceServiceFactory,
    user_service_factory: UserServiceFactory,
) -> None:
    await _segment_membership(
        message,
        command,
        audience_service_factory(session),
        user_service_factory(session),
        add=False,
    )


@router.message(Command("ad_segment_list"), OwnerFilter)
async def handle_ad_segment_list(
    message: Message,
    session: AsyncSession,
    audience_service_factory: AudienceServiceFactory,
) -> None:
    audience = audience_service_factory(session)
    segments = await audience.list_segments()
    if not segments:
        await message.answer("No segments yet. Create one with <code>/ad_segment_create</code>.")
        return
    lines = ["👥 <b>Audience segments</b>"]
    for seg in segments:
        count = await audience.count_members(seg.id)
        lines.append(f"<b>#{seg.id}</b> {escape(seg.name)} · {count} member(s)")
    await message.answer("\n".join(lines))


async def _segment_membership(
    message: Message,
    command: CommandObject,
    audience: AudienceService,
    users: UserService,
    *,
    add: bool,
) -> None:
    name, telegram_id = _parse_name_and_id(command.args)
    if name is None or telegram_id is None:
        verb = "ad_segment_add" if add else "ad_segment_remove"
        await message.answer(f"Usage: <code>/{verb} &lt;segment&gt; &lt;telegram_id&gt;</code>")
        return
    segment = await audience.find_segment(name)
    if segment is None:
        await message.answer(f"No segment named <code>{escape(name)}</code>.")
        return
    snap = await users.find(telegram_id)
    if snap is None:
        await message.answer(f"No user with telegram id <code>{telegram_id}</code>.")
        return
    if add:
        await audience.add_member(segment_id=segment.id, user_row_id=snap.id)
        await message.answer(f"✅ Added <code>{telegram_id}</code> to <b>{escape(name)}</b>.")
    else:
        await audience.remove_member(segment_id=segment.id, user_row_id=snap.id)
        await message.answer(f"Removed <code>{telegram_id}</code> from <b>{escape(name)}</b>.")


# --- ad-click callback (Task 9.4, flow 16.7 W6) ---------------------------
@router.callback_query(F.data.startswith("a|"))
async def handle_ad_click(
    callback: CallbackQuery,
    session: AsyncSession,
    ad_service_factory: AdServiceFactory,
    callback_signer: CallbackSigner,
) -> None:
    parsed = callback_signer.unpack(callback.data or "")
    if parsed is None or parsed.action != "a" or parsed.arg is None:
        await callback.answer()  # forged/garbled → ignore silently (Section 14.2)
        return
    await callback.answer()
    url = await ad_service_factory(session).record_click(parsed.arg, parsed.button_id)
    if url and isinstance(callback.message, Message):
        await callback.message.answer(f'🔗 <a href="{escape(url)}">Open the link</a>')


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


def _parse_audience_args(raw: str | None) -> tuple[str, list[tuple[str, str, str]]]:
    """Parse ``<mode> [!]dim:value …`` → (audience_mode, [(effect, dimension, value)]).

    A ``!`` prefix marks an exclude rule; otherwise the rule is an include rule. Raises
    ``ValueError`` on an unknown mode or dimension.
    """
    tokens = (raw or "").split()
    if not tokens:
        raise ValueError("provide a mode (all/include/exclude).")
    mode = tokens[0].lower()
    if mode not in (m.value for m in AudienceMode):
        raise ValueError(f"mode must be one of: {', '.join(m.value for m in AudienceMode)}.")
    rules: list[tuple[str, str, str]] = []
    for token in tokens[1:]:
        effect = AudienceEffect.INCLUDE.value
        body = token
        if body.startswith("!"):
            effect = AudienceEffect.EXCLUDE.value
            body = body[1:]
        if ":" not in body:
            raise ValueError(f"rule {token!r} must be dim:value.")
        dim_raw, value = body.split(":", 1)
        dimension = _DIMENSION_ALIASES.get(dim_raw.lower())
        if dimension is None:
            raise ValueError(f"unknown dimension {dim_raw!r}.")
        if not value:
            raise ValueError(f"rule {token!r} needs a value.")
        rules.append((effect, dimension, value))
    return mode, rules


def _parse_target_flags(raw: str | None) -> tuple[str | None, str | None]:
    """Parse ``[--lang xx] [--role xx]`` → (language, role)."""
    language: str | None = None
    role: str | None = None
    tokens = (raw or "").split()
    index = 0
    while index < len(tokens):
        if tokens[index] == "--lang" and index + 1 < len(tokens):
            language = tokens[index + 1]
            index += 2
        elif tokens[index] == "--role" and index + 1 < len(tokens):
            role = tokens[index + 1]
            index += 2
        else:
            index += 1
    return language, role


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


def _describe_target(language: str | None, role: str | None) -> str:
    parts = []
    if role is not None:
        parts.append(f"role={role}")
    if language is not None:
        parts.append(f"lang={language}")
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
def _format_ad_row(ad: Any) -> str:
    state = "✅" if ad.is_active else "⏸"
    target = ad.target_role or "all"
    return (
        f"{state} <b>#{ad.id}</b> {escape(ad.title)} "
        f"[{ad.type}] p{ad.priority} every {ad.show_every_n_downloads} · "
        f"target={target} · 👁 {ad.impressions} · 🖱 {ad.clicks}"
    )


def _format_ad_stats(ad: Any) -> str:
    return (
        f"📊 <b>Ad #{ad.id}</b> — {escape(ad.title)}\n"
        f"Impressions: <b>{ad.impressions}</b>\n"
        f"Clicks: <b>{ad.clicks}</b>\n"
        f"CTR: <b>{_ctr(ad.impressions, ad.clicks)}</b>"
    )


def _format_overall_stats(stats: AdStats) -> str:
    return (
        "📊 <b>Ad totals</b>\n"
        f"Ads: <b>{stats.total_ads}</b> ({stats.active_ads} active)\n"
        f"Impressions: <b>{stats.impressions}</b>\n"
        f"Clicks: <b>{stats.clicks}</b>\n"
        f"CTR: <b>{_ctr(stats.impressions, stats.clicks)}</b>"
    )


def _ctr(impressions: int, clicks: int) -> str:
    if impressions <= 0:
        return "—"
    return f"{clicks / impressions * 100:.1f}%"
