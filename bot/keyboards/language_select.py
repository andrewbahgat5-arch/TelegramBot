"""Language-selection inline keyboards (MASTER_PLAN Sprint 11.5).

One button per enabled locale (``core.i18n.list_enabled_locales()``), labeled with
its own native name — dropping in a new ``core/locales/<code>.json`` with
``_meta.enabled: true`` is all it takes for a new button to appear here, no code
change. Used from both the regular ``/start`` entry point and the admin panel's
"Language" section — one picker, multiple entry points.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.callbacks.factory import CallbackSigner
from core.i18n import list_enabled_locales, translate

# Sentinel "code" that means "show the picker" rather than "apply this language" —
# reuses the same signed `l` callback action/parsing path (Section 14.2 uniformity)
# instead of adding an unsigned or differently-shaped callback.
OPEN_PICKER_SENTINEL = ""


def build_change_language_button(signer: CallbackSigner, locale: str) -> InlineKeyboardMarkup:
    """A single "Change Language" button that opens the picker (e.g. under /start)."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=translate("language.change_button", locale),
        callback_data=signer.pack_language(OPEN_PICKER_SENTINEL),
    )
    return builder.as_markup()


def build_language_picker(signer: CallbackSigner) -> InlineKeyboardMarkup:
    """One button per enabled locale, labeled with its native name."""
    builder = InlineKeyboardBuilder()
    for meta in list_enabled_locales():
        builder.button(text=meta.native_name, callback_data=signer.pack_language(meta.code))
    builder.adjust(2)
    return builder.as_markup()
