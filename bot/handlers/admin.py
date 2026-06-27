"""Admin handlers (MASTER_PLAN Component 9.1 ``AdminHandlers``, Task 8.2).

In-bot administration for Owner and Moderator. Authorization lives in the
``RoleFilter`` (Section 9.1: handlers never decide authz); each command is gated by
the role its API counterpart requires (Section 20.2):

* **Staff** (owner or moderator): ``/stats``, ``/userinfo`` — read-only.
* **Owner only**: ``/users``, ``/ban``, ``/unban``, ``/setting_set``, ``/broadcast``.

``/settings`` now opens the inline Settings panel (``bot/handlers/admin_panel.py``,
Sprint 9.6); the old text-list command was retired. ``/setting_set`` remains as the
scriptable fallback.

Unauthorized users are **silently ignored** (item #18): there is no catch-all reply,
so a non-staff user's admin command matches no handler and the bot says nothing —
admin commands are invisible to normal users.

Handlers parse, delegate to a service, and format — no business logic (Section 9.1).
Per-request services arrive as aiogram workflow data factories; ``queue_service`` is a
process singleton injected directly.
"""

from __future__ import annotations

from collections.abc import Callable
from html import escape

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.role_filter import RoleFilter, StaffFilter
from core.logging import get_logger
from core.timeparse import parse_iso_datetime
from domain.entities.user import UserSnapshot
from domain.enums import UserRole
from services.broadcast_service import BroadcastService, InvalidBroadcastError
from services.queue_service import QueueService
from services.settings_service import (
    InvalidSettingValueError,
    SettingNotFoundError,
    SettingsService,
)
from services.user_service import UserService

router = Router(name="admin")
_log = get_logger("bot.handlers.admin")

UserServiceFactory = Callable[[AsyncSession], UserService]
SettingsServiceFactory = Callable[[AsyncSession], SettingsService]
BroadcastServiceFactory = Callable[[AsyncSession], BroadcastService]

OwnerFilter = RoleFilter(UserRole.OWNER)
_USERS_PAGE_SIZE = 30


@router.message(Command("stats"), StaffFilter)
async def handle_stats(
    message: Message,
    session: AsyncSession,
    user_service_factory: UserServiceFactory,
    queue_service: QueueService,
) -> None:
    stats = await user_service_factory(session).get_stats()
    depth = await queue_service.depth()
    active = await queue_service.active_count()
    await message.answer(
        "📊 <b>System stats</b>\n"
        f"Users: <b>{stats.total_users}</b> (banned: {stats.banned_users})\n"
        f"Lifetime downloads: <b>{stats.total_downloads}</b>\n"
        f"Queue: <b>{depth}</b> waiting, {active} in flight"
    )


@router.message(Command("userinfo"), StaffFilter)
async def handle_userinfo(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    user_service_factory: UserServiceFactory,
) -> None:
    telegram_id = _parse_int(command.args)
    if telegram_id is None:
        await message.answer("Usage: <code>/userinfo &lt;telegram_id&gt;</code>")
        return
    snap = await user_service_factory(session).find(telegram_id)
    if snap is None:
        await message.answer(f"No user with telegram id <code>{telegram_id}</code>.")
        return
    await message.answer(_format_userinfo(snap))


@router.message(Command("ban"), OwnerFilter)
async def handle_ban(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    user_service_factory: UserServiceFactory,
) -> None:
    telegram_id, reason = _parse_id_and_rest(command.args)
    if telegram_id is None:
        await message.answer("Usage: <code>/ban &lt;telegram_id&gt; [reason]</code>")
        return
    snap = await user_service_factory(session).ban(telegram_id, reason)
    if snap is None:
        await message.answer(f"No user with telegram id <code>{telegram_id}</code>.")
        return
    suffix = f" — {escape(reason)}" if reason else ""
    await message.answer(f"🚫 Banned <code>{telegram_id}</code>{suffix}.")


@router.message(Command("unban"), OwnerFilter)
async def handle_unban(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    user_service_factory: UserServiceFactory,
) -> None:
    telegram_id = _parse_int(command.args)
    if telegram_id is None:
        await message.answer("Usage: <code>/unban &lt;telegram_id&gt;</code>")
        return
    snap = await user_service_factory(session).unban(telegram_id)
    if snap is None:
        await message.answer(f"No user with telegram id <code>{telegram_id}</code>.")
        return
    await message.answer(f"✅ Unbanned <code>{telegram_id}</code>.")


@router.message(Command("setting_set"), OwnerFilter)
async def handle_setting_set(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    user: UserSnapshot,
    settings_service_factory: SettingsServiceFactory,
) -> None:
    key, value = _parse_key_value(command.args)
    if key is None or value is None:
        await message.answer("Usage: <code>/setting_set &lt;key&gt; &lt;value&gt;</code>")
        return
    service = settings_service_factory(session)
    try:
        await service.set_validated(key, value, updated_by=user.id)
    except SettingNotFoundError:
        await message.answer(f"Unknown setting key: <code>{escape(key)}</code>")
        return
    except InvalidSettingValueError as exc:
        await message.answer(f"Invalid value: {escape(str(exc))}")
        return
    await message.answer(f"✅ Updated <code>{escape(key)}</code> = {escape(value)}")


@router.message(Command("broadcast"), OwnerFilter)
async def handle_broadcast(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    user: UserSnapshot,
    broadcast_service_factory: BroadcastServiceFactory,
) -> None:
    text, language, role, at_raw = _parse_broadcast_args(command.args)
    scheduled_at = None
    if at_raw is not None:
        try:
            scheduled_at = parse_iso_datetime(at_raw)
        except ValueError:
            await message.answer(
                "Invalid <code>--at</code> time. Use ISO-8601, e.g. "
                "<code>--at 2026-07-01T12:00:00Z</code>."
            )
            return
    try:
        broadcast = await broadcast_service_factory(session).create(
            created_by_user_id=user.id,
            # The worker delivers broadcasts with HTML parse mode (to preserve wizard-
            # composed formatting), so escape the raw command text to render verbatim.
            message_text=escape(text),
            target_language=language,
            target_role=role,
            scheduled_at=scheduled_at,
        )
    except InvalidBroadcastError as exc:
        await message.answer(f"Cannot broadcast: {escape(str(exc))}")
        return
    target = _describe_target(language, role)
    when = f" — scheduled {scheduled_at:%Y-%m-%d %H:%M} UTC" if scheduled_at else ""
    await message.answer(
        f"📢 Broadcast #{broadcast.id} queued to "
        f"<b>{broadcast.expected_total}</b> users{target}{when}."
    )


@router.message(Command("users"), OwnerFilter)
async def handle_users(
    message: Message,
    session: AsyncSession,
    user_service_factory: UserServiceFactory,
) -> None:
    users = await user_service_factory(session).list_users(limit=_USERS_PAGE_SIZE)
    if not users:
        await message.answer("No users registered yet.")
        return
    lines = [f"👥 <b>Users</b> (first {len(users)})"]
    lines += [_format_user_row(snap) for snap in users]
    await message.answer("\n".join(lines))


def _format_user_row(snap: UserSnapshot) -> str:
    """One compact line per user for ``/users``: id, @username, name, lang, role, status."""
    username = f"@{escape(snap.username)}" if snap.username else "—"
    name = escape(snap.first_name) if snap.first_name else "—"
    lang = snap.language or "—"
    status = "🚫 banned" if snap.is_banned else "active"
    return (
        f"<code>{snap.telegram_id}</code> · {username} · {name} · "
        f"{lang} · {snap.role.value} · {status}"
    )


def _parse_int(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(raw.strip().split()[0])
    except (ValueError, IndexError):
        return None


def _parse_id_and_rest(raw: str | None) -> tuple[int | None, str | None]:
    if not raw:
        return None, None
    parts = raw.strip().split(maxsplit=1)
    try:
        telegram_id = int(parts[0])
    except (ValueError, IndexError):
        return None, None
    reason = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
    return telegram_id, reason


def _parse_key_value(raw: str | None) -> tuple[str | None, str | None]:
    if not raw:
        return None, None
    parts = raw.strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        return None, None
    return parts[0], parts[1].strip()


def _parse_broadcast_args(raw: str | None) -> tuple[str, str | None, str | None, str | None]:
    """Split ``<text> [--lang xx] [--role xx] [--at <iso>]`` into (text, lang, role, at).

    Flags may appear anywhere; the remaining tokens form the message text. An empty
    or flags-only message yields an empty text, which ``BroadcastService`` rejects.
    ``--at`` carries an ISO-8601 timestamp (validated by the caller).
    """
    if not raw:
        return "", None, None, None
    tokens = raw.split()
    language: str | None = None
    role: str | None = None
    at_raw: str | None = None
    text_tokens: list[str] = []
    index = 0
    while index < len(tokens):
        word = tokens[index]
        if word in ("--lang", "--role", "--at") and index + 1 < len(tokens):
            if word == "--lang":
                language = tokens[index + 1]
            elif word == "--role":
                role = tokens[index + 1]
            else:
                at_raw = tokens[index + 1]
            index += 2
            continue
        text_tokens.append(word)
        index += 1
    return " ".join(text_tokens), language, role, at_raw


def _describe_target(language: str | None, role: str | None) -> str:
    parts = []
    if role is not None:
        parts.append(f"role={role}")
    if language is not None:
        parts.append(f"lang={language}")
    return f" ({', '.join(parts)})" if parts else ""


def _format_userinfo(snap: UserSnapshot) -> str:
    flags = []
    if snap.is_banned:
        flags.append("🚫 banned")
    if snap.is_premium:
        flags.append("⭐ premium")
    status = ", ".join(flags) if flags else "active"
    name = escape(snap.first_name) if snap.first_name else "—"
    return (
        f"👤 <b>{name}</b> (<code>{snap.telegram_id}</code>)\n"
        f"Role: {snap.role.value} · {status}\n"
        f"Downloads: {snap.total_downloads} (today: {snap.daily_download_count})"
    )
