"""AuthMiddleware (MASTER_PLAN Component 9.1, Task 4.5).

Resolves the Telegram user to a ``users`` row (cache-first, D-014), records activity
(debounced), and rejects banned users with a friendly message before any handler
runs. The resolved :class:`UserSnapshot` is attached as ``data["user"]``.

Because repositories are bound to the per-update session, the middleware builds the
``UserService`` from a factory using ``data["session"]`` (set by
``DbSessionMiddleware``, which must run first).

New users are created with the configured ``default_locale`` (Sprint 11.5), never
Telegram's auto-detected ``language_code`` — that code isn't restricted to the
languages this bot actually catalogs (``core/locales/*.json``), so trusting it
verbatim could park a user on an unsupported/uncataloged value.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
)
from sqlalchemy.ext.asyncio import AsyncSession

from core.i18n import resolve_locale, translate
from domain.enums import UserRole
from services.settings_service import SettingsService
from services.template_service import TemplateService
from services.user_service import UserService

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]
UserServiceFactory = Callable[[AsyncSession], UserService]
SettingsServiceFactory = Callable[[AsyncSession], SettingsService]

_REPLY_COOLDOWN = 300
_reply_timestamps: dict[int, float] = {}

_STAFF_ROLES = frozenset({UserRole.OWNER, UserRole.MODERATOR})


class AuthMiddleware(BaseMiddleware):
    def __init__(
        self,
        user_service_factory: UserServiceFactory,
        *,
        default_locale: str,
        settings_service_factory: SettingsServiceFactory | None = None,
        template_service: TemplateService | None = None,
    ) -> None:
        self._user_service_factory = user_service_factory
        self._default_locale = default_locale
        self._settings_factory = settings_service_factory
        self._template_service = template_service

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        service = self._user_service_factory(data["session"])
        snapshot = await service.get_or_create_user(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            language=self._default_locale,
        )
        await service.record_activity(snapshot)

        locale = resolve_locale(snapshot.language)

        if snapshot.is_banned:
            await _reply_throttled(
                event, tg_user.id, "user.banned", locale, self._template_service
            )
            return None

        if snapshot.role not in _STAFF_ROLES and self._settings_factory is not None:
            try:
                if await self._settings_factory(data["session"]).get("maintenance_mode"):
                    await _reply_throttled(
                        event, tg_user.id, "system.maintenance", locale, self._template_service
                    )
                    return None
            except Exception:  # noqa: S110
                pass

        data["user"] = snapshot
        return await handler(event, data)


async def _reply_throttled(
    event: TelegramObject,
    tg_id: int,
    i18n_key: str,
    locale: str,
    template_service: TemplateService | None,
) -> None:
    now = time.monotonic()
    ts_key = hash((tg_id, i18n_key))
    if ts_key in _reply_timestamps and now - _reply_timestamps[ts_key] < _REPLY_COOLDOWN:
        return
    _reply_timestamps[ts_key] = now

    text = translate(i18n_key, locale)
    buttons = _template_buttons(i18n_key, locale, template_service)
    markup = (
        InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=b["text"], url=b["url"])] for b in buttons]
        )
        if buttons
        else None
    )
    if isinstance(event, Message):
        await event.answer(text, reply_markup=markup)
    elif isinstance(event, CallbackQuery):
        await event.answer(text, show_alert=True)


def _template_buttons(
    i18n_key: str, locale: str, template_service: TemplateService | None
) -> list[dict[str, str]]:
    if template_service is None:
        return []
    key_map = {"user.banned": "banned_message", "system.maintenance": "maintenance"}
    template_key = key_map.get(i18n_key)
    if template_key is None:
        return []
    return template_service.buttons_for(template_key, locale)
