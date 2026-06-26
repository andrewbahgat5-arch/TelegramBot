"""Admin inline control panel handlers (Sprint 9.6, F-2 / EP-22).

``/admin`` opens the root panel; ``/settings`` opens the Settings panel directly.
Both are ``StaffFilter`` (owner + moderator); a non-staff user matches no handler
and is silently ignored (item #18). Almost all administration then happens through
the inline keyboards — navigation and read views land here; write actions (settings
edits, user / ad management, broadcast, wizards) arrive in later 9.6 tasks.

No business logic (Section 9.1): :class:`PanelFilter` verifies + parses the signed
callback and injects ``panel``; handlers delegate to the existing services and
render, editing the panel's own message in place to keep the chat clean.

Authorization is layered (defense in depth on top of hiding write buttons from
moderators in the keyboard layer):

* read navigation — ``PanelFilter(mutating=False)`` + ``StaffFilter``;
* write actions — ``PanelFilter(mutating=True)`` + ``OwnerFilter``;
* a final ``P|`` fallback silently acks forged or unauthorized callbacks (no spinner,
  no leak).
"""

from __future__ import annotations

from collections.abc import Callable
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.callbacks.factory import CallbackSigner, ParsedPanel
from bot.filters.panel_filter import PanelFilter
from bot.filters.role_filter import RoleFilter, StaffFilter
from bot.keyboards.admin_panel import build_main_menu, build_section_menu, build_settings_menu
from bot.panel.registry import SECTIONS, SETTING_FIELDS
from core.logging import get_logger
from domain.entities.user import UserSnapshot
from domain.enums import UserRole
from services.admin_service import AdminService
from services.queue_service import QueueService
from services.settings_service import SettingsService
from services.user_service import UserService

router = Router(name="admin_panel")
_log = get_logger("bot.handlers.admin_panel")

UserServiceFactory = Callable[[AsyncSession], UserService]
SettingsServiceFactory = Callable[[AsyncSession], SettingsService]
AdminServiceFactory = Callable[[AsyncSession], AdminService]

OwnerFilter = RoleFilter(UserRole.OWNER)

_OWNER_ONLY_SECTIONS = frozenset(section.code for section in SECTIONS if section.owner_only)
_MAIN_TEXT = "🛠 <b>Admin Panel</b>\nChoose a section."
_LIST_LIMIT = 20


# --- entry commands -------------------------------------------------------
@router.message(Command("admin"), StaffFilter)
async def open_panel(message: Message, user: UserSnapshot, callback_signer: CallbackSigner) -> None:
    await message.answer(_MAIN_TEXT, reply_markup=build_main_menu(user.role, callback_signer))


@router.message(Command("settings"), StaffFilter)
async def open_settings(
    message: Message,
    session: AsyncSession,
    user: UserSnapshot,
    settings_service_factory: SettingsServiceFactory,
    callback_signer: CallbackSigner,
) -> None:
    text = await _settings_text(settings_service_factory(session))
    await message.answer(text, reply_markup=build_settings_menu(user.role, callback_signer))


# --- read navigation ------------------------------------------------------
@router.callback_query(PanelFilter(mutating=False), StaffFilter)
async def panel_navigate(
    callback: CallbackQuery,
    panel: ParsedPanel,
    session: AsyncSession,
    user: UserSnapshot,
    user_service_factory: UserServiceFactory,
    settings_service_factory: SettingsServiceFactory,
    ad_service_factory: Callable[[AsyncSession], object],
    admin_service_factory: AdminServiceFactory,
    queue_service: QueueService,
    callback_signer: CallbackSigner,
) -> None:
    # Owner-only sections are hidden from moderators; guard the callback too.
    if panel.section in _OWNER_ONLY_SECTIONS and user.role is not UserRole.OWNER:
        await callback.answer()
        return
    rendered = await _render(
        panel,
        user,
        session,
        callback_signer,
        user_service_factory,
        settings_service_factory,
        ad_service_factory,
        admin_service_factory,
        queue_service,
    )
    if rendered is not None and isinstance(callback.message, Message):
        text, markup = rendered
        await _safe_edit(callback.message, text, markup)
    await callback.answer()


# --- write actions (stubbed until later 9.6 tasks) ------------------------
@router.callback_query(PanelFilter(mutating=True), OwnerFilter)
async def panel_write(callback: CallbackQuery, panel: ParsedPanel) -> None:
    # Settings edits land in 9.6.5; users/ads/broadcast/wizards in 9.6.6 onward.
    await callback.answer("This action isn't available yet.", show_alert=False)


# --- forged / unauthorized fallback ---------------------------------------
@router.callback_query(F.data.startswith("P|"))
async def panel_ignore(callback: CallbackQuery) -> None:
    await callback.answer()  # silent: forged signature or a moderator's owner-only tap


# --- rendering ------------------------------------------------------------
async def _render(
    panel: ParsedPanel,
    user: UserSnapshot,
    session: AsyncSession,
    signer: CallbackSigner,
    user_factory: UserServiceFactory,
    settings_factory: SettingsServiceFactory,
    ad_factory: Callable[[AsyncSession], object],
    admin_factory: AdminServiceFactory,
    queue: QueueService,
) -> tuple[str, InlineKeyboardMarkup] | None:
    """Map a verified read callback to (message text, keyboard). None → just ack."""
    section, action = panel.section, panel.action
    role = user.role
    if section == "mn":
        return _MAIN_TEXT, build_main_menu(role, signer)
    if section == "s":
        return await _settings_text(settings_factory(session)), build_settings_menu(role, signer)
    if section == "t":
        return await _stats_text(user_factory(session), queue), build_section_menu(
            "t", role, signer
        )
    if section == "u":
        text = (
            await _users_text(user_factory(session), banned_only=False)
            if action == "ls"
            else "👥 <b>Users</b>\nList, look up, or manage a user."
        )
        return text, build_section_menu("u", role, signer)
    if section == "a":
        text = (
            await _ads_text(ad_factory(session))
            if action == "ls"
            else "📢 <b>Advertisements</b>\nManage campaigns."
        )
        return text, build_section_menu("a", role, signer)
    if section == "b":
        return "📣 <b>Broadcast</b>\nChoose an audience to message.", build_section_menu(
            "b", role, signer
        )
    if section == "m":
        return await _users_text(user_factory(session), banned_only=True), build_section_menu(
            "m", role, signer
        )
    if section == "h":
        return await _jobs_text(admin_factory(session)), build_section_menu("h", role, signer)
    if section == "d":
        text = (
            await _jobs_text(
                admin_factory(session), status="processing", title="⏳ <b>Active jobs</b>"
            )
            if action == "ls"
            else await _queue_text(queue)
        )
        return text, build_section_menu("d", role, signer)
    if section == "y":
        text = (
            await _errors_text(admin_factory(session))
            if action == "ls"
            else await _system_text(user_factory(session), settings_factory(session), queue)
        )
        return text, build_section_menu("y", role, signer)
    return None


async def _safe_edit(message: Message, text: str, markup: InlineKeyboardMarkup) -> None:
    try:
        await message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        pass  # "message is not modified" when re-opening the same screen — harmless


async def _stats_text(users: UserService, queue: QueueService) -> str:
    stats = await users.get_stats()
    depth, active = await queue.depth(), await queue.active_count()
    return (
        "📊 <b>Statistics</b>\n"
        f"Users: <b>{stats.total_users}</b> (banned {stats.banned_users})\n"
        f"Lifetime downloads: <b>{stats.total_downloads}</b>\n"
        f"Queue: <b>{depth}</b> waiting · {active} in flight"
    )


async def _users_text(users: UserService, *, banned_only: bool) -> str:
    rows = await users.list_users(limit=_LIST_LIMIT)
    if banned_only:
        rows = [row for row in rows if row.is_banned]
    title = "🚫 <b>Banned users</b>" if banned_only else "👥 <b>Users</b>"
    if not rows:
        empty = "No banned users." if banned_only else "No users yet."
        return f"{title}\n\n{empty}"
    return "\n".join([title, "", *(_user_row(row) for row in rows)])


def _user_row(snap: UserSnapshot) -> str:
    username = f"@{escape(snap.username)}" if snap.username else "—"
    marker = "🚫" if snap.is_banned else ("⭐" if snap.is_premium else "•")
    return f"{marker} <code>{snap.telegram_id}</code> · {username} · {snap.role.value}"


async def _ads_text(ad_service: object) -> str:
    ads = await ad_service.list_ads()  # type: ignore[attr-defined]  # AdService (Any-typed factory)
    if not ads:
        return "📢 <b>Advertisements</b>\n\nNo ads yet."
    lines = ["📢 <b>Advertisements</b>", ""]
    for ad in ads:
        state = "✅" if ad.is_active else "⏸"
        lines.append(
            f"{state} <b>#{ad.id}</b> {escape(ad.title)} · 👁 {ad.impressions} · 🖱 {ad.clicks}"
        )
    return "\n".join(lines)


async def _settings_text(settings: SettingsService) -> str:
    current = {view.key: view.value for view in await settings.list_all()}
    lines = ["⚙️ <b>Settings</b>", "Current values (tap a field to edit):", ""]
    for field in SETTING_FIELDS:
        lines.append(f"• {field.label}: <b>{escape(current.get(field.key, '—'))}</b>")
    return "\n".join(lines)


async def _jobs_text(
    admin: AdminService, *, status: str | None = None, title: str = "📂 <b>Recent activity</b>"
) -> str:
    jobs = await admin.list_jobs(limit=_LIST_LIMIT, status=status)
    if not jobs:
        return f"{title}\n\nNothing to show."
    lines = [title, ""]
    for job in jobs:
        lines.append(
            f"<code>{escape(job.id[:8])}</code> · {escape(job.status)} · "
            f"{escape(job.format)}/{escape(job.quality)}"
        )
    return "\n".join(lines)


async def _errors_text(admin: AdminService) -> str:
    errors = await admin.browse_errors(limit=_LIST_LIMIT)
    if not errors:
        return "⚠️ <b>Errors</b>\n\nNo recent errors. 🎉"
    lines = ["⚠️ <b>Recent errors</b>", ""]
    for err in errors:
        lines.append(
            f"<code>{err.created_at:%m-%d %H:%M}</code> · "
            f"{escape(err.error_type)}: {escape(err.message[:60])}"
        )
    return "\n".join(lines)


async def _queue_text(queue: QueueService) -> str:
    depth, active = await queue.depth(), await queue.active_count()
    return f"📥 <b>Downloads</b>\nQueue depth: <b>{depth}</b>\nIn flight: <b>{active}</b>"


async def _system_text(users: UserService, settings: SettingsService, queue: QueueService) -> str:
    stats = await users.get_stats()
    depth, active = await queue.depth(), await queue.active_count()
    maintenance = await settings.get_view("maintenance_mode")
    return (
        "🔧 <b>System</b>\n"
        f"Maintenance: <b>{escape(maintenance.value if maintenance else '—')}</b>\n"
        f"Users: <b>{stats.total_users}</b> · Downloads: <b>{stats.total_downloads}</b>\n"
        f"Queue: <b>{depth}</b> waiting · {active} in flight"
    )
