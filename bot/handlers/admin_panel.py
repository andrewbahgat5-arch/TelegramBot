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

import datetime
from collections.abc import Callable, Sequence
from html import escape
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.callbacks.factory import CallbackSigner, ParsedPanel
from bot.filters.panel_filter import PanelFilter
from bot.filters.role_filter import RoleFilter, StaffFilter
from bot.handlers import admin_wizard
from bot.keyboards.admin_panel import (
    build_ad_action_list,
    build_ad_detail,
    build_ad_list,
    build_confirm,
    build_input_prompt,
    build_main_menu,
    build_section_menu,
    build_setting_stepper,
    build_settings_menu,
    build_user_detail,
    build_user_list,
)
from bot.panel.registry import SECTIONS, SETTING_FIELDS, SettingField, setting_field
from bot.panel.states import PanelStates
from core.logging import get_logger
from domain.entities.user import UserSnapshot
from domain.enums import UserRole
from services.ad_service import AdService
from services.admin_service import AdminService
from services.audience_service import AudienceService
from services.broadcast_service import BroadcastService, InvalidBroadcastError
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
AdServiceFactory = Callable[[AsyncSession], AdService]
BroadcastServiceFactory = Callable[[AsyncSession], BroadcastService]
AudienceServiceFactory = Callable[[AsyncSession], AudienceService]

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
    state: FSMContext,
    user_service_factory: UserServiceFactory,
    settings_service_factory: SettingsServiceFactory,
    ad_service_factory: AdServiceFactory,
    admin_service_factory: AdminServiceFactory,
    queue_service: QueueService,
    callback_signer: CallbackSigner,
) -> None:
    await state.clear()  # navigating away cancels any pending guided input
    # "User Info" with no target → start the guided id-lookup wizard (9.6.8).
    if panel.section == "u" and panel.action == "inf" and panel.arg is None:
        await _arm_user_lookup(callback, state, callback_signer)
        return
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
    state: FSMContext,
    user_service_factory: UserServiceFactory,
    settings_service_factory: SettingsServiceFactory,
    admin_service_factory: AdminServiceFactory,
    ad_service_factory: AdServiceFactory,
    broadcast_service_factory: BroadcastServiceFactory,
    audience_service_factory: AudienceServiceFactory,
    callback_signer: CallbackSigner,
) -> None:
    if panel.section == "w":  # compose wizard — manages its own FSM state (no clear)
        await admin_wizard.dispatch(
            callback,
            panel,
            state,
            session=session,
            user=user,
            signer=callback_signer,
            ad_service_factory=ad_service_factory,
            broadcast_service_factory=broadcast_service_factory,
            audience_service_factory=audience_service_factory,
        )
        return
    await state.clear()  # a fresh write cancels any stale guided input ("ev" re-arms below)
    # Compose-wizard entry points (9.6.10): Ads "Create" / Broadcast "Create" + presets.
    if panel.section == "a" and panel.action == "cr":
        await admin_wizard.start(callback, state, callback_signer, kind="ad")
        return
    if panel.section == "a" and panel.action == "ed" and panel.arg is not None:
        # Full edit-in-wizard: load the existing ad into the compose wizard (Bug-fix sprint).
        await admin_wizard.start_edit(
            callback,
            panel.arg,
            state,
            callback_signer,
            ads=ad_service_factory(session),
            audience=audience_service_factory(session),
        )
        return
    if panel.section == "b" and panel.action in ("cr", "bf", "bp", "ba", "bl"):
        await admin_wizard.start(callback, state, callback_signer, kind="broadcast")
        return
    if panel.section == "s":  # Settings stepper / guided entry (9.6.5, 9.6.7)
        await _settings_write(
            callback, panel, settings_service_factory(session), user, callback_signer, state
        )
        return
    if panel.section == "u":  # Users management (9.6.6)
        await _users_write(
            callback,
            panel,
            user_service_factory(session),
            admin_service_factory(session),
            settings_service_factory(session),
            user,
            callback_signer,
        )
        return
    if panel.section == "a":  # Advertisements management (9.6.9)
        await _ads_write(
            callback,
            panel,
            ad_service_factory(session),
            broadcast_service_factory(session),
            user,
            callback_signer,
        )
        return
    # create/edit wizards land in 9.6.10.
    await callback.answer("This action isn't available yet.", show_alert=False)


async def _settings_write(
    callback: CallbackQuery,
    panel: ParsedPanel,
    settings: SettingsService,
    user: UserSnapshot,
    signer: CallbackSigner,
    state: FSMContext,
) -> None:
    """Open / step / type / save a numeric setting (LOCKED §13.4 keys only)."""
    field = setting_field(panel.arg) if panel.arg is not None else None
    if field is None:
        await callback.answer()
        return
    if panel.action == "ev":  # "✏️ Enter Value" → arm the guided-input wizard
        if isinstance(callback.message, Message):
            await state.set_state(PanelStates.setting_value)
            await state.update_data(
                field_index=field.index,
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
            )
            await _safe_edit(
                callback.message,
                _enter_value_text(field),
                build_input_prompt(signer, back=("s", "e", field.index), cancel=("s", "op", None)),
            )
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
        "Adjust with the buttons, or tap ✏️ Enter Value to type one, then 💾 Save."
    )


def _enter_value_text(field: SettingField) -> str:
    return (
        f"✏️ <b>{escape(field.label)}</b>\n\n"
        f"Send the new value in chat (a whole number between {field.min_value} and "
        f"{field.max_value})."
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
    admin: AdminService,
    settings: SettingsService,
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
                build_confirm(
                    signer, confirm=("u", confirmed, tid, None), cancel=("u", "inf", tid)
                ),
            )
        await callback.answer()
        return
    result = await _apply_user_action(users, action, tid)
    if result is None:
        await callback.answer("User not found.", show_alert=True)
        return
    _, toast = result
    view = await _user_detail_view(users, admin, settings, tid, actor.role, signer)
    if view is not None and isinstance(callback.message, Message):
        text, markup = view
        await _safe_edit(callback.message, text, markup)
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


async def _user_detail_view(
    users: UserService,
    admin: AdminService,
    settings: SettingsService,
    tid: int,
    role: UserRole,
    signer: CallbackSigner,
) -> tuple[str, InlineKeyboardMarkup] | None:
    """Build the extended User Info screen, or None if no such user."""
    snap = await users.find(tid)
    if snap is None:
        return None
    history_count = await admin.count_user_downloads(snap.id)
    active_jobs = await admin.count_user_active_jobs(snap.id)
    daily_limit = await settings.get(
        "premium_daily_limit" if snap.is_premium else "free_daily_limit"
    )
    text = _user_detail_text(
        snap, history_count=history_count, active_jobs=active_jobs, daily_limit=daily_limit
    )
    return text, build_user_detail(snap, role, signer)


def _user_detail_text(
    snap: UserSnapshot, *, history_count: int, active_jobs: int, daily_limit: object
) -> str:
    name = escape(snap.first_name) if snap.first_name else "—"
    username = f"@{escape(snap.username)}" if snap.username else "—"
    if snap.is_banned:
        status = "🚫 banned" + (f" — {escape(snap.ban_reason)}" if snap.ban_reason else "")
    else:
        status = "✅ active"
    premium = "⭐ yes" if snap.is_premium else "no"
    if snap.is_premium and snap.premium_expires_at is not None:
        premium += f" (until {snap.premium_expires_at:%Y-%m-%d})"
    active = "yes" if active_jobs > 0 else "none"
    return (
        f"👤 <b>{name}</b>\n"
        f"User ID: <code>{snap.telegram_id}</code>\n"
        f"Username: {username}\n"
        f"Language: {snap.language or '—'}\n"
        f"Role: {snap.role.value}\n"
        f"Status: {status}\n"
        f"Premium: {premium}\n"
        f"Joined: {_fmt_dt(snap.created_at)}\n"
        f"Last activity: {_fmt_dt(snap.last_activity_at)}\n"
        f"Total downloads: {snap.total_downloads}\n"
        f"Today: {snap.daily_download_count} / limit {daily_limit}\n"
        f"History entries: {history_count}\n"
        f"Active job: {active}"
    )


def _fmt_dt(value: datetime.datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value is not None else "—"


def _users_list_text(rows: list[UserSnapshot]) -> str:
    if not rows:
        return "👥 <b>Users</b>\n\nNo users yet."
    return f"👥 <b>Users</b> (first {len(rows)})\nTap a user to manage them."


def _user_lookup_text() -> str:
    return "🔍 <b>User Info</b>\n\nSend the user's Telegram ID in chat."


async def _arm_user_lookup(
    callback: CallbackQuery, state: FSMContext, signer: CallbackSigner
) -> None:
    """Prompt for a Telegram id and arm the user_lookup wizard."""
    if isinstance(callback.message, Message):
        await state.set_state(PanelStates.user_lookup)
        await state.update_data(
            chat_id=callback.message.chat.id, message_id=callback.message.message_id
        )
        await _safe_edit(
            callback.message,
            _user_lookup_text(),
            build_input_prompt(signer, back=("u", "op", None), cancel=("u", "op", None)),
        )
    await callback.answer()


# --- forged / unauthorized fallback ---------------------------------------
@router.callback_query(F.data.startswith("P|"))
async def panel_ignore(callback: CallbackQuery) -> None:
    await callback.answer()  # silent: forged signature or a moderator's owner-only tap


# --- guided input: a typed setting value (9.6.7) --------------------------
@router.message(PanelStates.setting_value, OwnerFilter)
async def on_setting_value(
    message: Message,
    state: FSMContext,
    bot: Bot,
    callback_signer: CallbackSigner,
) -> None:
    """Capture the value the Owner typed for ✏️ Enter Value → confirm screen before saving."""
    data = await state.get_data()
    index, chat_id, message_id = (
        data.get("field_index"),
        data.get("chat_id"),
        data.get("message_id"),
    )
    field = setting_field(index) if isinstance(index, int) else None
    if field is None or chat_id is None or message_id is None:
        await state.clear()
        return
    raw = (message.text or "").strip()
    try:
        value = int(raw)
    except ValueError:
        await message.reply("Please send a whole number, or tap ❌ Cancel.")
        return  # keep the state so the next message is still captured
    if not (field.min_value <= value <= field.max_value):
        await message.reply(f"Value must be between {field.min_value} and {field.max_value}.")
        return
    await state.clear()
    text = f"💾 <b>Confirm</b>\n\nSet <b>{escape(field.label)}</b> to <b>{value}</b>?"
    await bot.edit_message_text(
        text,
        chat_id=chat_id,
        message_id=message_id,
        reply_markup=build_confirm(
            callback_signer,
            confirm=("s", "sv", field.index, value),
            cancel=("s", "e", field.index),
        ),
    )


# --- guided input: a typed Telegram id for User Info (9.6.8) --------------
@router.message(PanelStates.user_lookup, StaffFilter)
async def on_user_lookup(
    message: Message,
    state: FSMContext,
    bot: Bot,
    session: AsyncSession,
    user: UserSnapshot,
    user_service_factory: UserServiceFactory,
    admin_service_factory: AdminServiceFactory,
    settings_service_factory: SettingsServiceFactory,
    callback_signer: CallbackSigner,
) -> None:
    """Capture the typed Telegram id and edit the panel to that user's extended detail."""
    data = await state.get_data()
    chat_id, message_id = data.get("chat_id"), data.get("message_id")
    if chat_id is None or message_id is None:
        await state.clear()
        return
    raw = (message.text or "").strip()
    try:
        tid = int(raw)
    except ValueError:
        await message.reply("Please send a numeric Telegram ID, or tap ❌ Cancel.")
        return  # keep the state for the next attempt
    await state.clear()
    view = await _user_detail_view(
        user_service_factory(session),
        admin_service_factory(session),
        settings_service_factory(session),
        tid,
        user.role,
        callback_signer,
    )
    if view is None:
        text: str = f"No user with id <code>{tid}</code>."
        markup = build_section_menu("u", user.role, callback_signer)
    else:
        text, markup = view
    await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup)


# --- guided input: compose wizard typed value / content (9.6.10) ----------
@router.message(PanelStates.wizard_text, OwnerFilter)
async def on_wizard_text(
    message: Message,
    state: FSMContext,
    bot: Bot,
    session: AsyncSession,
    callback_signer: CallbackSigner,
    ad_service_factory: AdServiceFactory,
) -> None:
    await admin_wizard.on_text(message, state, bot, session, callback_signer, ad_service_factory)


@router.message(PanelStates.wizard_content, OwnerFilter)
async def on_wizard_content(
    message: Message,
    state: FSMContext,
    bot: Bot,
    session: AsyncSession,
    callback_signer: CallbackSigner,
    ad_service_factory: AdServiceFactory,
) -> None:
    await admin_wizard.on_content(message, state, bot, session, callback_signer, ad_service_factory)


# --- rendering ------------------------------------------------------------
async def _render(
    panel: ParsedPanel,
    user: UserSnapshot,
    session: AsyncSession,
    signer: CallbackSigner,
    user_factory: UserServiceFactory,
    settings_factory: SettingsServiceFactory,
    ad_factory: AdServiceFactory,
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
        if action == "inf" and panel.arg is not None:
            view = await _user_detail_view(
                users, admin_factory(session), settings_factory(session), panel.arg, role, signer
            )
            if view is not None:
                return view
            return f"No user with id <code>{panel.arg}</code>.", build_section_menu(
                "u", role, signer
            )
        if action == "ls":
            rows = await users.list_users(limit=_LIST_LIMIT)
            return _users_list_text(rows), build_user_list(rows, signer)
        return "👥 <b>Users</b>\nTap 📋 List to browse and manage users.", build_section_menu(
            "u", role, signer
        )
    if section == "a":
        ads = ad_factory(session)
        if action == "inf" and panel.arg is not None:
            view = await _ad_detail_view(ads, panel.arg, role, signer)
            if view is not None:
                return view
            return f"No ad with id <code>{panel.arg}</code>.", build_section_menu("a", role, signer)
        if action == "ls":
            ad_rows = await ads.list_ads()
            return _ads_list_text(ad_rows), build_ad_list(ad_rows, signer)
        if action == "stt":
            return await _overall_stats_text(ads), build_section_menu("a", role, signer)
        return "📢 <b>Advertisements</b>\nManage campaigns.", build_section_menu("a", role, signer)
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


# Destructive / high-impact ad actions route through a confirm screen first.
_AD_CONFIRM = {
    "de": ("dec", "delete ad"),
    "bc": ("bcc", "broadcast to ALL users ad"),
}

# Top-level Manage-Campaigns actions that need an ad chosen first → render a picker.
_AD_PICKER_ACTIONS = frozenset({"en", "di", "de", "bc", "ed"})
_AD_PICKER_VERB = {
    "en": "enable",
    "di": "disable",
    "de": "delete",
    "bc": "broadcast",
    "ed": "edit",
}


def _ad_picker_text(action: str, rows: Sequence[Any]) -> str:
    if not rows:
        return "📢 <b>Advertisements</b>\n\nNo ads yet — create one first."
    verb = _AD_PICKER_VERB.get(action, "manage")
    return f"📢 <b>Pick an ad to {verb}</b>\nTap an ad below."


async def _ads_write(
    callback: CallbackQuery,
    panel: ParsedPanel,
    ads: AdService,
    broadcasts: BroadcastService,
    actor: UserSnapshot,
    signer: CallbackSigner,
) -> None:
    """Enable / Disable / Delete / Broadcast a selected ad; destructive steps confirm first."""
    ad_id, action = panel.arg, panel.action
    if ad_id is None:
        # A top-level Manage-Campaigns action (no ad chosen yet): show an ad picker whose
        # rows carry the same action + an ad id, so the next tap is fully targeted.
        if action in _AD_PICKER_ACTIONS:
            rows = await ads.list_ads()
            if isinstance(callback.message, Message):
                await _safe_edit(
                    callback.message,
                    _ad_picker_text(action, rows),
                    build_ad_action_list(rows, action, signer),
                )
            await callback.answer()
            return
        await callback.answer("Open 📋 List and tap an ad first.", show_alert=False)
        return
    if action in _AD_CONFIRM:  # render the confirm screen
        if await ads.get(ad_id) is None:
            await callback.answer("Ad not found.", show_alert=True)
            return
        confirmed, verb = _AD_CONFIRM[action]
        prompt = f"⚠️ <b>Confirm</b>\n\nReally {verb} #{ad_id}?"
        if isinstance(callback.message, Message):
            await _safe_edit(
                callback.message,
                prompt,
                build_confirm(
                    signer, confirm=("a", confirmed, ad_id, None), cancel=("a", "inf", ad_id)
                ),
            )
        await callback.answer()
        return
    if action == "dec":  # confirmed delete
        deleted = await ads.delete(ad_id)
        toast = f"🗑 Deleted ad #{ad_id}" if deleted else "Ad not found."
        rows = await ads.list_ads()
        if isinstance(callback.message, Message):
            await _safe_edit(callback.message, _ads_list_text(rows), build_ad_list(rows, signer))
        await callback.answer(toast)
        return
    if action == "bcc":  # confirmed broadcast to all
        try:
            broadcast = await broadcasts.create_from_ad(
                created_by_user_id=actor.id, advertisement_id=ad_id
            )
        except InvalidBroadcastError as exc:
            await callback.answer(f"Cannot broadcast: {exc}", show_alert=True)
            return
        await _rerender_ad_detail(callback, ads, ad_id, actor.role, signer)
        await callback.answer(f"📢 Queued to {broadcast.expected_total} users ✅")
        return
    if action in ("en", "di"):  # enable / disable directly
        ad = await ads.set_active(ad_id, action == "en")
        if ad is None:
            await callback.answer("Ad not found.", show_alert=True)
            return
        await _rerender_ad_detail(callback, ads, ad_id, actor.role, signer)
        await callback.answer("Enabled ✅" if action == "en" else "Disabled ⏸")
        return
    await callback.answer()


async def _rerender_ad_detail(
    callback: CallbackQuery, ads: AdService, ad_id: int, role: UserRole, signer: CallbackSigner
) -> None:
    view = await _ad_detail_view(ads, ad_id, role, signer)
    if view is not None and isinstance(callback.message, Message):
        text, markup = view
        await _safe_edit(callback.message, text, markup)


async def _ad_detail_view(
    ads: AdService, ad_id: int, role: UserRole, signer: CallbackSigner
) -> tuple[str, InlineKeyboardMarkup] | None:
    ad = await ads.get(ad_id)
    if ad is None:
        return None
    return _ad_detail_text(ad), build_ad_detail(ad, role, signer)


def _ad_detail_text(ad: Any) -> str:
    state = "✅ active" if ad.is_active else "⏸ disabled"
    ctr = f"{ad.clicks / ad.impressions * 100:.1f}%" if ad.impressions else "—"
    return (
        f"📢 <b>{escape(ad.title)}</b> (#{ad.id})\n"
        f"Type: {ad.type} · {state}\n"
        f"Target: {ad.target_role or 'all'} · priority {ad.priority}\n"
        f"Every {ad.show_every_n_downloads} downloads\n"
        f"👁 {ad.impressions} · 🖱 {ad.clicks} · CTR {ctr}"
    )


def _ads_list_text(rows: Sequence[Any]) -> str:
    if not rows:
        return "📢 <b>Advertisements</b>\n\nNo ads yet. Create one (wizard, 9.6.10)."
    return f"📢 <b>Advertisements</b> ({len(rows)})\nTap an ad to manage it."


async def _overall_stats_text(ads: AdService) -> str:
    stats = await ads.overall_stats()
    ctr = f"{stats.clicks / stats.impressions * 100:.1f}%" if stats.impressions else "—"
    return (
        "📊 <b>Ad totals</b>\n"
        f"Ads: {stats.total_ads} ({stats.active_ads} active)\n"
        f"👁 {stats.impressions} · 🖱 {stats.clicks} · CTR {ctr}"
    )


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
