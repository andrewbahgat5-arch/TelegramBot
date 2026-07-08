"""Admin inline control panel keyboards (Sprint 9.6, F-2 / EP-22; Sprint 11.5 i18n).

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
* **Localized (Sprint 11.5):** every button label is a ``core.i18n`` translation key
  resolved with the viewer's own ``locale`` — the registry stores keys, not literal text.

Every ``callback_data`` is signed via :class:`CallbackSigner` (``P`` namespace) and so
stays within Telegram's 64-byte limit.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.callbacks.factory import CallbackSigner
from bot.panel.registry import (
    AUDIENCE_OPTIONS,
    PLACEMENT_OPTIONS,
    SECTIONS,
    SETTING_FIELDS,
    SETTINGS_INFO,
    SUBMENUS,
    SettingField,
    is_write_action,
)
from bot.panel.wizard import (
    STEP_PREVIEW,
    WizardState,
    next_step,
    prev_step,
    step_index,
)
from core.i18n import translate
from domain.entities.user import UserSnapshot
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
    locale: str,
    *,
    back: tuple[str, str] | None = None,
    cancel: tuple[str, str] | None = None,
    home: bool = True,
) -> list[InlineKeyboardButton]:
    """A consistent ⬅️ Back · ❌ Cancel · 🏠 Home row. ``back``/``cancel`` are (section, action)."""
    row: list[InlineKeyboardButton] = []
    if back is not None:
        row.append(_btn(signer, translate("common.back", locale), back[0], back[1]))
    if cancel is not None:
        row.append(_btn(signer, translate("common.cancel", locale), cancel[0], cancel[1]))
    if home:
        row.append(_btn(signer, translate("common.home", locale), "mn", "hm"))
    return row


def build_main_menu(role: UserRole, signer: CallbackSigner, locale: str) -> InlineKeyboardMarkup:
    """The root panel. Owner-only sections are dropped for moderators."""
    buttons = [
        _btn(signer, translate(section.label_key, locale), section.code, "op")
        for section in SECTIONS
        if not section.owner_only or role is UserRole.OWNER
    ]
    return InlineKeyboardMarkup(inline_keyboard=_chunk(buttons))


def build_section_menu(
    section: str, role: UserRole, signer: CallbackSigner, locale: str
) -> InlineKeyboardMarkup:
    """A section's static action menu. Write-tier items are hidden from moderators."""
    items = SUBMENUS.get(section, ())
    buttons = [
        _btn(signer, translate(item.label_key, locale), section, item.action, item.arg)
        for item in items
        if role is UserRole.OWNER or not is_write_action(item.action)
    ]
    rows = _chunk(buttons)
    rows.append(nav_row(signer, locale, back=("mn", "op")))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_platform_stats(
    signer: CallbackSigner, locale: str, *, period_index: int, role: UserRole
) -> InlineKeyboardMarkup:
    """Platform-analytics screen: time filters (compact), owner-only CSV export, Back.

    The four period buttons carry ``stt`` with arg 0..3 (today/week/month/all); the
    active period is marked. Export is a write action, so it is hidden from moderators
    here (keyboard layer) and blocked by ``OwnerFilter`` (filter layer).
    """
    filters = [
        _btn(
            signer,
            f"{'• ' if period_index == idx else ''}{translate(key, locale)}",
            "t",
            "stt",
            idx,
        )
        for idx, key in enumerate(
            (
                "panel.platforms.filter.today",
                "panel.platforms.filter.week",
                "panel.platforms.filter.month",
                "panel.platforms.filter.all",
            )
        )
    ]
    rows = [filters]  # all four on one compact row (§2.2 rule 3)
    if role is UserRole.OWNER:
        rows.append([_btn(signer, translate("panel.platforms.export", locale), "t", "csv")])
    rows.append(nav_row(signer, locale, back=("t", "op")))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_template_list(
    views: Sequence[Any], signer: CallbackSigner, locale: str
) -> InlineKeyboardMarkup:
    """One tappable row per editable template (Sprint 13.8); custom rows marked ✏️."""
    rows = [
        [
            _btn(
                signer,
                f"{'✏️' if view.is_custom else '📄'} {view.key}",
                "tp",
                "inf",
                index,
            )
        ]
        for index, view in enumerate(views)
    ]
    rows.append(nav_row(signer, locale, back=("mn", "op")))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_template_detail(
    index: int, *, is_custom: bool, signer: CallbackSigner, locale: str
) -> InlineKeyboardMarkup:
    """A template's edit screen: Edit Content, Reset (only if custom), Back (13.8)."""
    rows = [[_btn(signer, translate("panel.templates.edit", locale), "tp", "ed", index)]]
    if is_custom:
        rows.append([_btn(signer, translate("panel.templates.reset", locale), "tp", "rs", index)])
    rows.append(nav_row(signer, locale, back=("tp", "op")))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_export_formats(signer: CallbackSigner, locale: str) -> InlineKeyboardMarkup:
    """Format picker for subscriber export (Sprint 13.6): CSV / JSON + Back."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(signer, translate("panel.users.export_csv", locale), "u", "exc"),
                _btn(signer, translate("panel.users.export_json", locale), "u", "exj"),
            ],
            nav_row(signer, locale, back=("u", "op")),
        ]
    )


def build_settings_menu(
    role: UserRole, signer: CallbackSigner, locale: str
) -> InlineKeyboardMarkup:
    """Settings list. Owner gets one edit button per stepper field; moderators get none.

    Current values are rendered into the message body by the handler (read-only view).
    Owner gets a stepper edit button per numeric field (write); the Cache / Languages
    info screens are read affordances shown to all staff.
    """
    buttons: list[InlineKeyboardButton] = []
    if role is UserRole.OWNER:
        buttons += [
            _btn(signer, translate(field.label_key, locale), "s", "e", field.index)
            for field in SETTING_FIELDS
        ]
    buttons += [
        _btn(signer, translate(item.label_key, locale), "s", "inf", item.index)
        for item in SETTINGS_INFO
    ]
    rows = _chunk(buttons)
    rows.append(nav_row(signer, locale, back=("mn", "op")))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_setting_stepper(
    field: SettingField, value: int, signer: CallbackSigner, locale: str
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
        [_btn(signer, translate("common.save", locale), "s", "sv", field.index, value)],
        [_btn(signer, translate("panel.settings.enter_value", locale), "s", "ev", field.index)],
        nav_row(signer, locale, back=("s", "op")),
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_input_prompt(
    signer: CallbackSigner,
    locale: str,
    *,
    back: tuple[str, str, int | None],
    cancel: tuple[str, str, int | None],
) -> InlineKeyboardMarkup:
    """The ❌ Cancel / ⬅️ Back row shown while waiting for the user to type a value."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(signer, translate("common.cancel", locale), cancel[0], cancel[1], cancel[2]),
                _btn(signer, translate("common.back", locale), back[0], back[1], back[2]),
            ]
        ]
    )


def build_confirm(
    signer: CallbackSigner,
    locale: str,
    *,
    confirm: tuple[str, str, int | None, int | None],
    cancel: tuple[str, str, int | None],
) -> InlineKeyboardMarkup:
    """The ✅ Confirm / ❌ Cancel screen for a destructive or to-be-saved action.

    ``confirm`` is (section, action, arg, value) carrying the write to perform (``value``
    lets a confirmed settings save carry the typed number); ``cancel`` is
    (section, action, arg) routing back to a menu or detail screen.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(
                    signer,
                    translate("common.confirm", locale),
                    confirm[0],
                    confirm[1],
                    confirm[2],
                    confirm[3],
                ),
                _btn(signer, translate("common.cancel", locale), cancel[0], cancel[1], cancel[2]),
            ]
        ]
    )


def build_ad_conflict_confirm(
    signer: CallbackSigner,
    locale: str,
    *,
    keep: tuple[str, str, int | None],
    replace: tuple[str, str, int | None],
    cancel: tuple[str, str, int | None],
) -> InlineKeyboardMarkup:
    """The Keep both / Replace existing / Cancel screen for a placement conflict (#9).

    Keep both is listed first as the recommended, non-destructive default; Replace disables
    the currently-active ad(s); Cancel aborts without changing anything. Each tuple is
    (section, action, arg) carrying the resolution to perform.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(
                    signer,
                    translate("panel.ads.conflict.keep_both", locale),
                    keep[0],
                    keep[1],
                    keep[2],
                )
            ],
            [
                _btn(
                    signer,
                    translate("panel.ads.conflict.replace", locale),
                    replace[0],
                    replace[1],
                    replace[2],
                )
            ],
            [_btn(signer, translate("common.cancel", locale), cancel[0], cancel[1], cancel[2])],
        ]
    )


def build_user_list(
    users: list[UserSnapshot], signer: CallbackSigner, locale: str
) -> InlineKeyboardMarkup:
    """Tappable user rows (one per row) → each opens that user's detail screen."""
    rows = [
        [_btn(signer, _user_button_label(snap), "u", "inf", snap.telegram_id)] for snap in users
    ]
    rows.append(nav_row(signer, locale, back=("u", "op")))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _user_button_label(snap: UserSnapshot) -> str:
    marker = "🚫" if snap.is_banned else ("⭐" if snap.is_premium else "👤")
    name = snap.first_name or snap.username or str(snap.telegram_id)
    return f"{marker} {snap.telegram_id} · {name}"[:60]


def build_ad_list(ads: Sequence[Any], signer: CallbackSigner, locale: str) -> InlineKeyboardMarkup:
    """Tappable ad rows (one per row) → each opens that ad's detail screen."""
    rows = [[_btn(signer, _ad_button_label(ad), "a", "inf", ad.id)] for ad in ads]
    rows.append(nav_row(signer, locale, back=("a", "op")))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _ad_button_label(ad: Any) -> str:
    state = "✅" if ad.is_active else "⏸"
    return f"{state} #{ad.id} {ad.title}"[:60]


def build_ad_action_list(
    ads: Sequence[Any], action: str, signer: CallbackSigner, locale: str
) -> InlineKeyboardMarkup:
    """Pick which ad a top-level Manage-Campaigns action applies to.

    The section-menu Enable/Disable/Delete/Broadcast/Edit buttons carry no ad id; tapping
    one lists the ads with each row carrying that same ``action`` plus the ad's id, so the
    selected row re-enters the write handler fully targeted (no dead-end, Bug-fix sprint).
    """
    rows = [[_btn(signer, _ad_button_label(ad), "a", action, ad.id)] for ad in ads]
    rows.append(nav_row(signer, locale, back=("a", "op")))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_ad_detail(
    ad: Any, role: UserRole, signer: CallbackSigner, locale: str
) -> InlineKeyboardMarkup:
    """An ad's detail screen with owner-only actions reflecting its current state.

    Enable/Disable toggle directly; Delete and Broadcast (to all users) route through a
    confirm screen (destructive / high-impact, Owner #4).
    """
    rows: list[list[InlineKeyboardButton]] = []
    if role is UserRole.OWNER:
        aid = ad.id
        actions = [
            _btn(signer, translate("panel.action.disable", locale), "a", "di", aid)
            if ad.is_active
            else _btn(signer, translate("panel.action.enable", locale), "a", "en", aid),
            _btn(signer, translate("panel.action.broadcast", locale), "a", "bc", aid),
            _btn(signer, translate("panel.action.delete", locale), "a", "de", aid),
        ]
        rows = _chunk(actions)
    rows.append(nav_row(signer, locale, back=("a", "ls")))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_user_detail(
    snap: UserSnapshot, role: UserRole, signer: CallbackSigner, locale: str
) -> InlineKeyboardMarkup:
    """A user's detail screen. Contextual write actions (owner-only) reflect current state.

    Owner targets expose no action buttons (an owner can't be banned or demoted via the
    panel). Destructive actions (Ban / Remove Premium / Make-or-Remove Admin) route through
    a confirm screen; additive ones (Unban / Upgrade Premium) act directly.
    """
    rows: list[list[InlineKeyboardButton]] = []
    if role is UserRole.OWNER and snap.role is not UserRole.OWNER:
        tid = snap.telegram_id
        actions = [
            _btn(signer, translate("panel.action.unban", locale), "u", "ubn", tid)
            if snap.is_banned
            else _btn(signer, translate("panel.action.ban", locale), "u", "ban", tid),
            _btn(signer, translate("panel.menu.u.remove_premium", locale), "u", "rp", tid)
            if snap.is_premium
            else _btn(signer, translate("panel.menu.u.upgrade_premium", locale), "u", "up", tid),
            _btn(signer, translate("panel.menu.u.remove_admin", locale), "u", "rma", tid)
            if snap.role is UserRole.MODERATOR
            else _btn(signer, translate("panel.menu.u.make_admin", locale), "u", "mka", tid),
        ]
        rows = _chunk(actions)
    rows.append(nav_row(signer, locale, back=("u", "ls")))
    return InlineKeyboardMarkup(inline_keyboard=rows)


# --- compose wizard (Sprint 9.6, D-057/D-059) -----------------------------
# Every wizard callback rides the "w" section; all its actions are write-tier (absent
# from READ_ACTIONS), so they are owner-only and hidden from moderators. Step ids ride as
# the compact ``arg`` int (``step_index``); option ids as ``arg`` from the registries.


def _w(
    signer: CallbackSigner,
    label: str,
    action: str,
    arg: int | None = None,
    value: int | None = None,
) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=label, callback_data=signer.pack_panel("w", action, arg, value)
    )


def _wizard_controls(
    signer: CallbackSigner,
    state: WizardState,
    step_id: str,
    locale: str,
    *,
    can_save: bool = False,
) -> list[list[InlineKeyboardButton]]:
    """Back/Next (or Save) + Cancel/Home, honouring the edit-from-preview hub."""
    rows: list[list[InlineKeyboardButton]] = []
    if state.return_to == "preview":  # reached via Edit ▸ — one button back to the hub
        rows.append(
            [_w(signer, translate("panel.wizard.done", locale), "go", step_index(STEP_PREVIEW))]
        )
    else:
        advance: list[InlineKeyboardButton] = []
        nxt = prev_step(state.kind, step_id)
        if nxt is not None:
            advance.append(_w(signer, translate("common.back", locale), "go", step_index(nxt)))
        if can_save:
            advance.append(_w(signer, translate("common.save", locale), "sv"))
        else:
            forward = next_step(state.kind, step_id)
            if forward is not None:
                advance.append(
                    _w(signer, translate("panel.wizard.next", locale), "go", step_index(forward))
                )
        if advance:
            rows.append(advance)
    rows.append(
        [
            _w(signer, translate("common.cancel", locale), "cx"),
            _btn(signer, translate("common.home", locale), "mn", "hm"),
        ]
    )
    return rows


def _mark(active: bool) -> str:
    return "☑" if active else "☐"


def build_wizard_audience(
    state: WizardState, signer: CallbackSigner, locale: str
) -> InlineKeyboardMarkup:
    from bot.panel.wizard import STEP_AUDIENCE

    rows: list[list[InlineKeyboardButton]] = []
    modes = [
        ("all", translate("panel.audience.mode.all", locale)),
        ("include", translate("panel.audience.mode.include", locale)),
        ("exclude", translate("panel.audience.mode.exclude", locale)),
    ]
    rows.append(
        [
            _w(signer, f"{'•' if state.audience_mode == code else ' '} {label}", "am", idx)
            for idx, (code, label) in enumerate(modes)
        ]
    )
    taken = {(e, d, v) for e, d, v in state.rules}
    option_buttons: list[InlineKeyboardButton] = []
    for opt in AUDIENCE_OPTIONS:
        opt_label = translate(opt.label_key, locale)
        if opt.value is None:  # typed sub-input: show how many such rules exist
            count = sum(1 for e, d, _v in state.rules if e == opt.effect and d == opt.dimension)
            label = f"{opt_label}" + (f" ({count})" if count else "")
        else:
            # Mutual exclusivity: hide a target already chosen on the opposite side, so the
            # admin can never create an Include+Exclude conflict (Owner #1/#2/#3). It
            # reappears the moment the opposite selection is removed.
            opposite = "exclude" if opt.effect == "include" else "include"
            if (opposite, opt.dimension, opt.value) in taken:
                continue
            active = [opt.effect, opt.dimension, opt.value] in state.rules
            label = f"{_mark(active)} {opt_label}"
        option_buttons.append(_w(signer, label, "atg", opt.index))
    rows.extend(_chunk(option_buttons))
    rows.extend(_wizard_controls(signer, state, STEP_AUDIENCE, locale))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_wizard_placement(
    state: WizardState, signer: CallbackSigner, locale: str
) -> InlineKeyboardMarkup:
    from bot.panel.wizard import STEP_PLACEMENT

    buttons = [
        _w(
            signer,
            f"{_mark(opt.code in state.placements)} {translate(opt.label_key, locale)}",
            "ptg",
            opt.index,
        )
        for opt in PLACEMENT_OPTIONS
    ]
    rows = _chunk(buttons)
    rows.extend(_wizard_controls(signer, state, STEP_PLACEMENT, locale))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_wizard_settings(
    state: WizardState, signer: CallbackSigner, locale: str
) -> InlineKeyboardMarkup:
    from bot.panel.wizard import STEP_SETTINGS

    rows: list[list[InlineKeyboardButton]] = [
        [
            _w(
                signer,
                f"{_mark(state.enabled)} {translate('panel.wizard.enabled_toggle', locale)}",
                "en",
            )
        ],
        [
            _w(signer, "➖", "pr", None, state.priority - 1),  # noqa: RUF001
            _w(
                signer,
                translate("panel.wizard.priority_label", locale, priority=state.priority),
                "pr",
                None,
                state.priority,
            ),
            _w(signer, "➕", "pr", None, state.priority + 1),  # noqa: RUF001
        ],
    ]
    if state.kind == "ad":
        freq = max(1, state.frequency)
        rows.append(
            [
                _w(signer, "➖", "fr", None, max(1, freq - 1)),  # noqa: RUF001
                _w(
                    signer,
                    translate("panel.wizard.frequency_label", locale, frequency=freq),
                    "fr",
                    None,
                    freq,
                ),
                _w(signer, "➕", "fr", None, freq + 1),  # noqa: RUF001
            ]
        )
    rows.append(
        [
            _w(signer, translate("panel.wizard.internal_name", locale), "in"),
            _w(signer, translate("panel.wizard.notes", locale), "no"),
        ]
    )
    rows.extend(_wizard_controls(signer, state, STEP_SETTINGS, locale))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_wizard_content(
    state: WizardState, signer: CallbackSigner, locale: str
) -> InlineKeyboardMarkup:
    from bot.panel.wizard import STEP_CONTENT

    rows: list[list[InlineKeyboardButton]] = [
        [_w(signer, translate("panel.wizard.send_content", locale), "ct")]
    ]
    if state.content_mode is not None:
        button_row = [_w(signer, translate("panel.wizard.add_button", locale), "ba")]
        if state.buttons:
            button_row.append(
                _w(
                    signer,
                    translate("panel.wizard.clear_buttons", locale, count=len(state.buttons)),
                    "bc",
                )
            )
        rows.append(button_row)
    rows.extend(_wizard_controls(signer, state, STEP_CONTENT, locale))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_wizard_preview(
    state: WizardState, signer: CallbackSigner, locale: str
) -> InlineKeyboardMarkup:
    """Preview = the edit hub: jump to any section, then return here (Owner #10)."""
    from bot.panel.wizard import (
        STEP_AUDIENCE,
        STEP_CONTENT,
        STEP_PLACEMENT,
        STEP_SETTINGS,
        has_step,
    )

    edits = [
        _w(signer, translate("panel.wizard.edit_audience", locale), "ed", step_index(STEP_AUDIENCE))
    ]
    if has_step(state.kind, STEP_PLACEMENT):
        edits.append(
            _w(
                signer,
                translate("panel.wizard.edit_placement", locale),
                "ed",
                step_index(STEP_PLACEMENT),
            )
        )
    if has_step(state.kind, STEP_SETTINGS):
        edits.append(
            _w(
                signer,
                translate("panel.wizard.edit_settings", locale),
                "ed",
                step_index(STEP_SETTINGS),
            )
        )
    edits.append(
        _w(signer, translate("panel.wizard.edit_content", locale), "ed", step_index(STEP_CONTENT))
    )
    rows = _chunk(edits)
    rows.append(
        [
            _w(signer, translate("common.save", locale), "sv"),
            _w(signer, translate("common.cancel", locale), "cx"),
        ]
    )
    rows.append([_btn(signer, translate("common.home", locale), "mn", "hm")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_wizard_input_prompt(
    signer: CallbackSigner, locale: str, *, back_step: int
) -> InlineKeyboardMarkup:
    """Cancel/Back row shown while the wizard waits for typed input or content."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _w(signer, translate("common.back", locale), "go", back_step),
                _w(signer, translate("common.cancel", locale), "cx"),
            ]
        ]
    )
