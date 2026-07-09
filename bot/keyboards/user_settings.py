"""User Settings screen keyboard (item #10).

One row per toggle (❌/✅ + label), rendered data-drivenly from ``SETTING_TOGGLES`` so a
new toggle is a registry entry, not a keyboard change; then a Back-to-Start row.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.callbacks.factory import CallbackSigner
from core.i18n import translate
from services.user_preference_service import SETTING_TOGGLES, UserPreferences


def build_user_settings(
    prefs: UserPreferences, signer: CallbackSigner, locale: str
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for toggle in SETTING_TOGGLES:
        on = bool(getattr(prefs, toggle.field))
        icon = "✅" if on else "❌"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{icon} {translate(toggle.label_key, locale)}",
                    callback_data=signer.pack_user_setting(toggle.index),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=translate("common.back", locale),
                callback_data=signer.pack_user_setting(-2),  # -2 = back to Start
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
