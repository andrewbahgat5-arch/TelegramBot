"""Cookie pool admin surface (DESIGN_COOKIE_POOL.md §10, §12).

Everything an admin needs happens in Telegram — there is deliberately no server-side
step. ``/cookies`` opens the pool; a notification's **Replace** button deep-links into
the same flow, so there is one implementation rather than two.

Safety properties this module is responsible for:

* **Owner-only.** These are account credentials, not settings.
* **Signed callbacks.** Every button carries an HMAC (``CallbackSigner.pack_panel``),
  so a forged ``callback_data`` cannot target another cookie.
* **Nothing changes until it is proven.** Validate → canary → compare-and-swap; a
  failure at any gate leaves the existing cookie exactly where it was.
* **The upload is deleted.** A cookies.txt sitting in chat history is a live Google
  session; the message goes as soon as the bytes are read.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.callbacks.factory import CallbackSigner
from bot.filters.role_filter import RoleFilter
from bot.panel.states import PanelStates
from core.i18n import Translator
from core.logging import get_logger
from domain.entities.cookie import CookieSnapshot
from domain.entities.user import UserSnapshot
from domain.enums import UserRole
from domain.enums.cookie_health import SELECTABLE_HEALTH, CookieHealth
from services.cookie_admin_service import CookieAdminService

router = Router(name="cookies")
_log = get_logger("bot.handlers.cookies")

# Cookies are account credentials, not settings: Owner only, never moderators.
OwnerFilter = RoleFilter(UserRole.OWNER)

#: Panel section code for every cookie callback.
SECTION = "ck"

#: Joiner for multi-line panel bodies.
NEWLINE = "\n"

CookieAdminFactory = Callable[[], CookieAdminService]

_MAX_UPLOAD_BYTES = 1024 * 1024

_STATUS_ICON = {
    CookieHealth.HEALTHY: "🟢",
    CookieHealth.WARNING: "🟡",
    CookieHealth.EXPIRED: "🔴",
    CookieHealth.INVALID: "🔴",
    CookieHealth.DISABLED: "⚪",
}


def replace_callback(signer: CallbackSigner) -> Callable[[int], str]:
    """Builder handed to ``AdminNotificationService`` for the notification button.

    Injected as a plain callable so the service never imports the bot layer.
    """

    def build(cookie_id: int) -> str:
        return signer.pack_panel(SECTION, "rep", cookie_id)

    return build


# ----------------------------------------------------------------- rendering ---


def _fmt_time(value: datetime.datetime | None, translate: Translator, locale: str) -> str:
    if value is None:
        return translate("cookies.detail.never", locale)
    return value.strftime("%Y-%m-%d %H:%M UTC")


def _pool_text(cookies: list[CookieSnapshot], translate: Translator, locale: str) -> str:
    healthy = sum(1 for c in cookies if c.status in SELECTABLE_HEALTH)
    lines = [translate("cookies.title", locale, healthy=healthy, total=len(cookies))]
    if not cookies:
        lines += ["", translate("cookies.empty", locale)]
        return "\n".join(lines)
    lines.append("")
    # Worst first: an admin opening this screen wants the problem, not the roll-call.
    order = {
        CookieHealth.EXPIRED: 0,
        CookieHealth.INVALID: 1,
        CookieHealth.WARNING: 2,
        CookieHealth.DISABLED: 3,
        CookieHealth.HEALTHY: 4,
    }
    for cookie in sorted(cookies, key=lambda c: (order.get(c.status, 9), c.label)):
        rate = cookie.success_rate
        rate_text = f"{rate * 100:.1f}%" if rate is not None else "—"
        egress = cookie.egress_id or "—"
        lines.append(
            f"{_STATUS_ICON.get(cookie.status, '•')} <b>{cookie.label}</b>  "
            f"{egress}  {rate_text}"
        )
    return "\n".join(lines)


def _pool_markup(
    cookies: list[CookieSnapshot], signer: CallbackSigner, translate: Translator, locale: str
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{_STATUS_ICON.get(c.status, '•')} {c.label}",
                callback_data=signer.pack_panel(SECTION, "view", c.id),
            )
        ]
        for c in sorted(cookies, key=lambda c: c.label)
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=translate("cookies.btn_add", locale),
                callback_data=signer.pack_panel(SECTION, "add"),
            ),
            InlineKeyboardButton(
                text=translate("cookies.btn_refresh", locale),
                callback_data=signer.pack_panel(SECTION, "list"),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _detail_text(cookie: CookieSnapshot, translate: Translator, locale: str) -> str:
    rate = cookie.success_rate
    total = cookie.total_success + cookie.total_auth_failures + cookie.total_other_failures
    failed = cookie.total_auth_failures + cookie.total_other_failures
    lines = [
        f"{_STATUS_ICON.get(cookie.status, '•')} <b>{cookie.label}</b> · "
        f"{cookie.status.value.upper()} · v{cookie.file_version}",
        "",
        f"{translate('cookies.detail.requests', locale)}: {total} · "
        f"✅ {cookie.total_success} · ❌ {failed}",
        f"{translate('cookies.detail.success_rate', locale)}: "
        f"{f'{rate * 100:.1f}%' if rate is not None else '—'}",
        f"{translate('cookies.detail.last_used', locale)}: "
        f"{_fmt_time(cookie.last_used_at, translate, locale)}",
        f"{translate('cookies.detail.last_success', locale)}: "
        f"{_fmt_time(cookie.last_success_at, translate, locale)}",
        f"{translate('cookies.detail.last_failure', locale)}: "
        f"{_fmt_time(cookie.last_failure_at, translate, locale)}"
        + (f" — {cookie.last_failure_reason}" if cookie.last_failure_reason else ""),
        f"{translate('cookies.detail.egress', locale)}: {cookie.egress_id or '—'}",
    ]
    if cookie.cooldown_until is not None:
        lines.append(
            translate(
                "cookies.detail.cooldown",
                locale,
                until=_fmt_time(cookie.cooldown_until, translate, locale),
            )
        )
    return "\n".join(lines)


def _detail_markup(
    cookie: CookieSnapshot, signer: CallbackSigner, translate: Translator, locale: str
) -> InlineKeyboardMarkup:
    toggle = (
        ("cookies.btn_enable", "ena")
        if cookie.status is CookieHealth.DISABLED
        else ("cookies.btn_disable", "dis")
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("cookies.btn_replace", locale),
                    callback_data=signer.pack_panel(SECTION, "rep", cookie.id),
                ),
                InlineKeyboardButton(
                    text=translate("cookies.btn_test", locale),
                    callback_data=signer.pack_panel(SECTION, "test", cookie.id),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate(toggle[0], locale),
                    callback_data=signer.pack_panel(SECTION, toggle[1], cookie.id),
                ),
                InlineKeyboardButton(
                    text=translate("cookies.btn_history", locale),
                    callback_data=signer.pack_panel(SECTION, "hist", cookie.id),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate("cookies.btn_back", locale),
                    callback_data=signer.pack_panel(SECTION, "list"),
                ),
            ],
        ]
    )


# ------------------------------------------------------------------ handlers ---


@router.message(Command("cookies"), OwnerFilter)
async def open_pool(
    message: Message,
    cookie_admin_factory: CookieAdminFactory,
    callback_signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> None:
    cookies = await cookie_admin_factory().list_pool()
    await message.answer(
        _pool_text(cookies, translate, locale),
        reply_markup=_pool_markup(cookies, callback_signer, translate, locale),
    )


@router.callback_query(F.data.startswith("P|ck|"), OwnerFilter)
async def on_cookie_action(
    callback: CallbackQuery,
    state: FSMContext,
    user: UserSnapshot,
    cookie_admin_factory: CookieAdminFactory,
    callback_signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> None:
    parsed = callback_signer.unpack_panel(callback.data or "")
    if parsed is None or parsed.section != SECTION:
        await callback.answer()  # forged/garbled → ignore silently
        return

    service = cookie_admin_factory()

    if parsed.action == "list":
        cookies = await service.list_pool()
        await _edit(
            callback,
            _pool_text(cookies, translate, locale),
            _pool_markup(cookies, callback_signer, translate, locale),
        )
        await callback.answer()
        return

    if parsed.action == "add":
        await state.set_state(PanelStates.cookie_upload)
        await state.update_data(cookie_id=None, file_version=None)
        await _reply(callback, translate("cookies.upload.prompt_new", locale))
        await callback.answer()
        return

    if parsed.arg is None:
        await callback.answer()
        return
    cookie = await service.get(parsed.arg)
    if cookie is None:
        await callback.answer(translate("cookies.not_found", locale), show_alert=True)
        return

    if parsed.action == "view":
        await _edit(
            callback,
            _detail_text(cookie, translate, locale),
            _detail_markup(cookie, callback_signer, translate, locale),
        )
    elif parsed.action == "rep":
        # The FSM carries the version the admin is replacing, so a concurrent replace
        # is detected at commit time instead of silently clobbering the newer file.
        await state.set_state(PanelStates.cookie_upload)
        await state.update_data(cookie_id=cookie.id, file_version=cookie.file_version)
        await _reply(callback, translate("cookies.upload.prompt", locale, label=cookie.label))
    elif parsed.action == "hist":
        events = await service.history(cookie.id)
        lines = [translate("cookies.history.title", locale, label=cookie.label), ""]
        if not events:
            lines.append(translate("cookies.history.empty", locale))
        for record in events:
            when = record.created_at.strftime("%m-%d %H:%M") if record.created_at else "—"
            status = f" → {record.to_status}" if record.to_status else ""
            detail = f" · {record.reason[:60]}" if record.reason else ""
            lines.append(f"<code>{when}</code> {record.event}{status}{detail}")
        await _edit(
            callback,
            NEWLINE.join(lines),
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=translate("cookies.btn_back", locale),
                            callback_data=callback_signer.pack_panel(
                                SECTION, "view", cookie.id
                            ),
                        )
                    ]
                ]
            ),
        )
    elif parsed.action == "test":
        await callback.answer(translate("cookies.test.running", locale, label=cookie.label))
        result = await service.test(cookie.id)
        key = "cookies.test.ok" if result.ok else "cookies.test.failed"
        await _reply(
            callback, translate(key, locale, label=cookie.label, detail=result.detail)
        )
        return
    elif parsed.action in {"dis", "ena"}:
        enabled = parsed.action == "ena"
        updated = await service.set_enabled(
            cookie.id, enabled=enabled, actor_user_id=user.id
        )
        await _reply(
            callback,
            translate(
                "cookies.enabled" if enabled else "cookies.disabled",
                locale,
                label=cookie.label,
            ),
        )
        if updated is not None:
            await _edit(
                callback,
                _detail_text(updated, translate, locale),
                _detail_markup(updated, callback_signer, translate, locale),
            )
    await callback.answer()


@router.message(PanelStates.cookie_upload, OwnerFilter)
async def on_cookie_upload(
    message: Message,
    state: FSMContext,
    bot: Bot,
    user: UserSnapshot,
    cookie_admin_factory: CookieAdminFactory,
    translate: Translator,
    locale: str,
) -> None:
    """Receive the uploaded cookies.txt, verify it, and swap in only that cookie."""
    if message.text and message.text.strip().lower() in {"/cancel", "cancel"}:
        await state.clear()
        await message.reply(translate("cookies.upload.cancelled", locale))
        return
    if message.document is None:
        # Keep the state so the next upload is still captured.
        await message.reply(translate("cookies.upload.not_a_file", locale))
        return
    if (message.document.file_size or 0) > _MAX_UPLOAD_BYTES:
        await message.reply(translate("cookies.upload.too_large", locale))
        return

    data = await state.get_data()
    await state.clear()
    cookie_id = data.get("cookie_id")
    expected_version = data.get("file_version")

    buffer = await bot.download(message.document)
    content = buffer.read() if buffer is not None else b""

    # The uploaded file is a live Google session; get it out of the chat immediately.
    await _delete_quietly(message)

    notice = await message.answer(translate("cookies.upload.testing", locale))
    service = cookie_admin_factory()
    # The INTERNAL users.id — youtube_cookies.created_by is a FK to it. Passing the
    # Telegram id here produced a ForeignKeyViolation on the very first real upload.
    actor = user.id

    if cookie_id is None:
        result = await service.add(content, actor_user_id=actor)
    else:
        current = await service.get(int(cookie_id))
        if current is not None and expected_version is not None and (
            current.file_version != int(expected_version)
        ):
            await notice.edit_text(translate("cookies.upload.conflict", locale))
            return
        result = await service.replace(int(cookie_id), content, actor_user_id=actor)

    healthy, total = await service.pool_summary()
    if not result.ok:
        key = {
            "invalid": "cookies.upload.invalid",
            "canary_failed": "cookies.upload.canary_failed",
            "conflict": "cookies.upload.conflict",
        }.get(result.kind, "cookies.upload.invalid")
        await notice.edit_text(translate(key, locale, reason=result.detail))
        return

    await notice.edit_text(
        translate(
            "cookies.upload.added" if result.kind == "added" else "cookies.upload.replaced",
            locale,
            label=result.label,
            version=result.version,
            detail=result.detail,
            healthy=healthy,
            total=total,
        )
    )


# -------------------------------------------------------------------- helpers ---


async def _reply(callback: CallbackQuery, text: str) -> None:
    """Answer in the callback's chat when that message is still accessible."""
    if isinstance(callback.message, Message):
        await callback.message.answer(text)


async def _edit(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(text, reply_markup=markup)
        except Exception as exc:  # "not modified", or the message is gone
            _log.debug("cookie_panel_edit_skipped", error=str(exc))


async def _delete_quietly(message: Message) -> None:
    """Bots may delete incoming messages in private chats — best-effort."""
    try:
        await message.delete()
    except Exception as exc:
        _log.info("cookie_upload_delete_failed", error=str(exc))
