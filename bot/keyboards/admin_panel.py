"""Admin inline control panel keyboards (Sprint 9.6, F-2 / EP-22).

Pure presentation: functions that turn the panel *registry* (``bot.panel.registry``)
plus the viewer's role into signed :class:`InlineKeyboardMarkup`. No business logic,
no service calls — handlers (``bot/handlers/admin_panel.py``) read data and pick the
builder; these only render.

Design goals honored here:

* **Registry-driven / extensible (#1, #6):** the main menu and submenus are generated
  from ``SECTIONS`` / ``SUBMENUS`` — adding a section or a future plugin module needs
  no change to these builders.
* **Role-aware (#2 authz):** write-tier buttons are *hidden* (not disabled) from
  moderators, classified by the same :func:`is_write_action` the ``PanelFilter`` uses;
  owner-only sections are dropped from the main menu.
* **Consistent navigation (#2):** :func:`nav_row` appends ⬅️ Back / 🏠 Home (and ❌ Cancel
  where applicable) to every submenu.
* **Confirmation (#4):** :func:`build_confirm` renders the ✅ Confirm / ❌ Cancel screen
  every destructive action routes through.
* **Stepper:** :func:`build_setting_stepper` renders minus / plus / 💾 Save with the
  candidate value carried (signed) in the callback, clamped to the field's UI guard rails.

Every ``callback_data`` is signed via :class:`CallbackSigner` (``P`` namespace) and so
stays within Telegram's 64-byte limit.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.callbacks.factory import CallbackSigner
from bot.panel.registry import (
    SECTIONS,
    SETTING_FIELDS,
    SETTINGS_INFO,
    SUBMENUS,
    SettingField,
    is_write_action,
)
from domain.enums import UserRole

_ROW_WIDTH = 2


def _btn(
    signer: CallbackSigner,
    label: str,
    section: str,
    action: str,
    arg: int | None = None,
    value: int | None = None,
) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=label, callback_data=signer.pack_panel(section, action, arg, value)
    )


def _chunk(buttons: list[InlineKeyboardButton]) -> list[list[InlineKeyboardButton]]:
    return [buttons[i : i + _ROW_WIDTH] for i in range(0, len(buttons), _ROW_WIDTH)]


def nav_row(
    signer: CallbackSigner,
    *,
    back: tuple[str, str] | None = None,
    cancel: tuple[str, str] | None = None,
    home: bool = True,
) -> list[InlineKeyboardButton]:
    """A consistent ⬅️ Back · ❌ Cancel · 🏠 Home row. ``back``/``cancel`` are (section, action)."""
    row: list[InlineKeyboardButton] = []
    if back is not None:
        row.append(_btn(signer, "⬅️ Back", back[0], back[1]))
    if cancel is not None:
        row.append(_btn(signer, "❌ Cancel", cancel[0], cancel[1]))
    if home:
        row.append(_btn(signer, "🏠 Home", "mn", "hm"))
    return row


def build_main_menu(role: UserRole, signer: CallbackSigner) -> InlineKeyboardMarkup:
    """The root panel. Owner-only sections are dropped for moderators."""
    buttons = [
        _btn(signer, section.label, section.code, "op")
        for section in SECTIONS
        if not section.owner_only or role is UserRole.OWNER
    ]
    return InlineKeyboardMarkup(inline_keyboard=_chunk(buttons))


def build_section_menu(
    section: str, role: UserRole, signer: CallbackSigner
) -> InlineKeyboardMarkup:
    """A section's static action menu. Write-tier items are hidden from moderators."""
    items = SUBMENUS.get(section, ())
    buttons = [
        _btn(signer, item.label, section, item.action, item.arg)
        for item in items
        if role is UserRole.OWNER or not is_write_action(item.action)
    ]
    rows = _chunk(buttons)
    rows.append(nav_row(signer, back=("mn", "op")))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_settings_menu(role: UserRole, signer: CallbackSigner) -> InlineKeyboardMarkup:
    """Settings list. Owner gets one edit button per stepper field; moderators get none.

    Current values are rendered into the message body by the handler (read-only view).
    Owner gets a stepper edit button per numeric field (write); the Cache / Languages
    info screens are read affordances shown to all staff.
    """
    buttons: list[InlineKeyboardButton] = []
    if role is UserRole.OWNER:
        buttons += [_btn(signer, field.label, "s", "e", field.index) for field in SETTING_FIELDS]
    buttons += [_btn(signer, item.label, "s", "inf", item.index) for item in SETTINGS_INFO]
    rows = _chunk(buttons)
    rows.append(nav_row(signer, back=("mn", "op")))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_setting_stepper(
    field: SettingField, value: int, signer: CallbackSigner
) -> InlineKeyboardMarkup:
    """The minus / plus / 💾 Save stepper for one numeric setting (owner-only screen).

    The candidate ``value`` rides (signed) in the decrement / increment / Save callbacks,
    clamped to the field's UI guard rails. The current value is shown in the message body.
    """
    decremented = max(field.min_value, value - field.step)
    incremented = min(field.max_value, value + field.step)
    rows = [
        [
            _btn(signer, "➖", "s", "-", field.index, decremented),  # noqa: RUF001
            _btn(signer, "➕", "s", "+", field.index, incremented),  # noqa: RUF001
        ],
        [_btn(signer, "💾 Save", "s", "sv", field.index, value)],
        nav_row(signer, back=("s", "op")),
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_confirm(
    signer: CallbackSigner,
    *,
    confirm: tuple[str, str, int | None],
    cancel: tuple[str, str],
) -> InlineKeyboardMarkup:
    """The ✅ Confirm / ❌ Cancel screen for a destructive action.

    ``confirm`` is (section, action, arg) carrying the write to perform; ``cancel`` is
    (section, action) routing back to a menu.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(signer, "✅ Confirm", confirm[0], confirm[1], confirm[2]),
                _btn(signer, "❌ Cancel", cancel[0], cancel[1]),
            ]
        ]
    )
