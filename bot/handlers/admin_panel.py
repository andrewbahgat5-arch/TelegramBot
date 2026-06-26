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
from bot.keyboards.admin_panel import (
    build_confirm,
    build_main_menu,
    build_section_menu,
    build_setting_stepper,
    build_settings_menu,
    build_user_detail,
    build_user_list,
)
from bot.panel.registry import SECTIONS, SETTING_FIELDS, SettingField, setting_field
from core.logging import get_logger
from domain.entities.user import UserSnapshot
from domain.enums import UserRole
from services.admin_service import AdminService
from services.queue_service import QueueService
from services.settings_service import (
    InvalidSettingValueError,
    SettingNotFoundError,
    SettingsService,
)
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


# --- write actions --------------------------------------------------------
@router.callback_query(PanelFilter(mutating=True), OwnerFilter)
async def panel_write(
    callback: CallbackQuery,
    panel: ParsedPanel,
    session: AsyncSession,
    user: UserSnapshot,
    user_service_factory: UserServiceFactory,
    settings_service_factory: SettingsServiceFactory,
    callback_signer: CallbackSigner,
) -> None:
    if panel.section == "s":  # Settings stepper (9.6.5)
        await _settings_write(
            callback, panel, settings_service_factory(session), user, callback_signer
        )
        return
    if panel.section == "u":  # Users management (9.6.6)
        await _users_write(callback, panel, user_service_factory(session), user, callback_signer)
        return
    # ads / broadcast / wizards land in 9.6.7 onward.
    await callback.answer("This action isn't available yet.", show_alert=False)


async def _settings_write(
    callback: CallbackQuery,
    panel: ParsedPanel,
    settings: SettingsService,
    user: UserSnapshot,
    signer: CallbackSigner,
) -> None:
    """Open / step / save a numeric setting via the stepper (LOCKED §13.4 keys only)."""
    field = setting_field(panel.arg) if panel.arg is not None else None
    if field is None:
        await callback.answer()
        return
    if panel.action == "sv":  # persist the candidate value
        value = _clamp(field, panel.value if panel.value is not None else field.min_value)
        try:
            await settings.set_validated(field.key, str(value), updated_by=user.id)
        except (SettingNotFoundError, InvalidSettingValueError) as exc:
            await callback.answer(f"Couldn't save: {exc}", show_alert=True)
            return
        if isinstance(callback.message, Message):
            await _safe_edit(
                callback.message,
                await _settings_text(settings),
                build_settings_menu(user.role, signer),
            )
        await callback.answer(f"Saved · {field.label} = {value} ✅")
        return
    # "e" opens the stepper at the live value; "-"/"+" carry the candidate already
    # clamped by the keyboard builder.
    if panel.action == "e":
        value = await _current_int(settings, field)
    else:  # "-" or "+"
        value = panel.value if panel.value is not None else await _current_int(settings, field)
    value = _clamp(field, value)
    if isinstance(callback.message, Message):
        await _safe_edit(
            callback.message,
            _stepper_text(field, value),
            build_setting_stepper(field, value, signer),
        )
    await callback.answer()


def _clamp(field: SettingField, value: int) -> int:
    return max(field.min_value, min(field.max_value, value))


async def _current_int(settings: SettingsService, field: SettingField) -> int:
    view = await settings.get_view(field.key)
    if view is None:
        return field.min_value
    try:
        return int(view.value)
    except ValueError:
        return field.min_value


def _stepper_text(field: SettingField, value: int) -> str:
    return (
        f"⚙️ <b>{escape(field.label)}</b>\n\n"
        f"Current value: <b>{value}</b>\n"
        f"Allowed: {field.min_value} to {field.max_value} (step {field.step})\n\n"
        "Adjust with the buttons, then 💾 Save."
    )


# Destructive user actions: open a confirm screen first. Maps the open action →
# (confirmed action, human verb for the prompt). Additive actions (ubn/up) act directly.
_USER_CONFIRM = {
    "ban": ("banc", "ban"),
    "rp": ("rpc", "remove premium from"),
    "mka": ("mkac", "make an admin"),
    "rma": ("rmac", "remove admin from"),
}


async def _users_write(
    callback: CallbackQuery,
    panel: ParsedPanel,
    users: UserService,
    actor: UserSnapshot,
    signer: CallbackSigner,
) -> None:
    """Ban / Unban / Premium / Admin on a selected user, destructive steps behind a confirm."""
    tid, action = panel.arg, panel.action
    if tid is None:  # a top-level submenu button without a target
        await callback.answer("Open 📋 List and tap a user first.", show_alert=False)
        return
    if action in _USER_CONFIRM:  # render the confirm screen
        snap = await users.find(tid)
        if snap is None:
            await callback.answer("User not found.", show_alert=True)
            return
        confirmed, verb = _USER_CONFIRM[action]
        prompt = f"⚠️ <b>Confirm</b>\n\nReally {verb} <code>{tid}</code>?"
        if isinstance(callback.message, Message):
            await _safe_edit(
                callback.message,
                prompt,
                build_confirm(signer, confirm=("u", confirmed, tid), cancel=("u", "inf", tid)),
            )
        await callback.answer()
        return
    result = await _apply_user_action(users, action, tid)
    if result is None:
        await callback.answer("User not found.", show_alert=True)
        return
    snap, toast = result
    if isinstance(callback.message, Message):
        await _safe_edit(
            callback.message, _user_detail_text(snap), build_user_detail(snap, actor.role, signer)
        )
    await callback.answer(toast)


async def _apply_user_action(
    users: UserService, action: str, tid: int
) -> tuple[UserSnapshot, str] | None:
    """Perform a (possibly already-confirmed) user write. Returns (snapshot, toast) or None."""
    if action == "ubn":
        snap = await users.unban(tid)
        return (snap, "✅ Unbanned") if snap else None
    if action == "up":
        snap = await users.set_premium(tid, is_premium=True)
        return (snap, "⭐ Premium granted") if snap else None
    if action == "banc":
        snap = await users.ban(tid)
        return (snap, "🚫 Banned") if snap else None
    if action == "rpc":
        snap = await users.set_premium(tid, is_premium=False)
        return (snap, "Premium removed") if snap else None
    if action == "mkac":
        snap = await users.set_role(tid, UserRole.MODERATOR)
        return (snap, "🛡 Promoted to admin") if snap else None
    if action == "rmac":
        snap = await users.set_role(tid, UserRole.USER)
        return (snap, "Admin removed") if snap else None
    return None


async def _user_detail(
    users: UserService, tid: int | None, role: UserRole, signer: CallbackSigner
) -> tuple[str, InlineKeyboardMarkup]:
    if tid is None:
        return "👥 <b>Users</b>\nOpen 📋 List and tap a user to manage them.", build_section_menu(
            "u", role, signer
        )
    snap = await users.find(tid)
    if snap is None:
        return f"No user with id <code>{tid}</code>.", build_section_menu("u", role, signer)
    return _user_detail_text(snap), build_user_detail(snap, role, signer)


def _user_detail_text(snap: UserSnapshot) -> str:
    flags = []
    if snap.is_banned:
        flags.append("🚫 banned" + (f" — {escape(snap.ban_reason)}" if snap.ban_reason else ""))
    if snap.is_premium:
        flags.append("⭐ premium")
    status = ", ".join(flags) if flags else "active"
    name = escape(snap.first_name) if snap.first_name else "—"
    username = f"@{escape(snap.username)}" if snap.username else "—"
    return (
        f"👤 <b>{name}</b> (<code>{snap.telegram_id}</code>)\n"
        f"Username: {username}\n"
        f"Role: {snap.role.value} · {status}\n"
        f"Downloads: {snap.total_downloads} (today {snap.daily_download_count})"
    )


def _users_list_text(rows: list[UserSnapshot]) -> str:
    if not rows:
        return "👥 <b>Users</b>\n\nNo users yet."
    return f"👥 <b>Users</b> (first {len(rows)})\nTap a user to manage them."


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
        if action == "inf":
            return _settings_info_text(panel.arg), build_settings_menu(role, signer)
        return await _settings_text(settings_factory(session)), build_settings_menu(role, signer)
    if section == "t":
        return await _stats_text(user_factory(session), queue), build_section_menu(
            "t", role, signer
        )
    if section == "u":
        users = user_factory(session)
        if action == "inf":
            return await _user_detail(users, panel.arg, role, signer)
        if action == "ls":
            rows = await users.list_users(limit=_LIST_LIMIT)
            return _users_list_text(rows), build_user_list(rows, signer)
        return "👥 <b>Users</b>\nTap 📋 List to browse and manage users.", build_section_menu(
            "u", role, signer
        )
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


def _settings_info_text(index: int | None) -> str:
    """Read-only info for the Cache / Languages submenu items (no LOCKED key to edit)."""
    if index == 0:
        return (
            "🗃 <b>Cache</b>\n\n"
            "Recently fetched files and metadata are cached in Redis to skip re-downloads. "
            "There is no tunable cache key in the panel — TTLs are configured via the "
            "<code>CACHE_*</code> environment settings."
        )
    if index == 1:
        return (
            "🌐 <b>Languages</b>\n\n"
            "The UI language follows each user's Telegram client. There is no editable "
            "language setting key; translations ship with the bot."
        )
    return "📋 <b>Info</b>\n\nNothing to show."


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
