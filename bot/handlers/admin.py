"""Admin handlers (MASTER_PLAN Component 9.1 ``AdminHandlers``, Task 8.2).

In-bot administration for Owner and Moderator. Authorization lives in the
``RoleFilter`` (Section 9.1: handlers never decide authz); each command is gated by
the role its API counterpart requires (Section 20.2):

* **Staff** (owner or moderator): ``/stats``, ``/userinfo``, ``/settings`` — read-only.
* **Owner only**: ``/ban``, ``/unban``, ``/setting_set``, ``/broadcast`` — mutating.

A trailing catch-all replies "not permitted" when a gated handler's role check fails
(it is registered last, so it only runs after the role-gated handlers decline).

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
_ADMIN_COMMANDS = ["stats", "userinfo", "ban", "unban", "settings", "setting_set", "broadcast"]
_DENIED_TEXT = "⛔ You don't have permission to use that command."


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


@router.message(Command("settings"), StaffFilter)
async def handle_settings(
    message: Message,
    session: AsyncSession,
    settings_service_factory: SettingsServiceFactory,
) -> None:
    views = await settings_service_factory(session).list_all()
    if not views:
        await message.answer("No settings are configured.")
        return
    lines = ["⚙️ <b>Settings</b>"]
    lines += [f"<code>{escape(v.key)}</code> = {escape(v.value)} ({v.value_type})" for v in views]
    await message.answer("\n".join(lines))


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
    text, language, role = _parse_broadcast_args(command.args)
    try:
        broadcast = await broadcast_service_factory(session).create(
            created_by_user_id=user.id,
            message_text=text,
            target_language=language,
            target_role=role,
        )
    except InvalidBroadcastError as exc:
        await message.answer(f"Cannot broadcast: {escape(str(exc))}")
        return
    target = _describe_target(language, role)
    await message.answer(
        f"📢 Broadcast #{broadcast.id} queued to <b>{broadcast.expected_total}</b> users{target}."
    )


@router.message(Command(commands=_ADMIN_COMMANDS))
async def handle_admin_denied(message: Message) -> None:
    """Runs only when a role-gated admin handler above declined (insufficient role)."""
    await message.answer(_DENIED_TEXT)


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


def _parse_broadcast_args(raw: str | None) -> tuple[str, str | None, str | None]:
    """Split ``<text> [--lang xx] [--role xx]`` into (text, language, role).

    Flags may appear anywhere; the remaining tokens form the message text. An empty
    or flags-only message yields an empty text, which ``BroadcastService`` rejects.
    """
    if not raw:
        return "", None, None
    tokens = raw.split()
    language: str | None = None
    role: str | None = None
    text_tokens: list[str] = []
    index = 0
    while index < len(tokens):
        word = tokens[index]
        if word in ("--lang", "--role") and index + 1 < len(tokens):
            if word == "--lang":
                language = tokens[index + 1]
            else:
                role = tokens[index + 1]
            index += 2
            continue
        text_tokens.append(word)
        index += 1
    return " ".join(text_tokens), language, role


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
