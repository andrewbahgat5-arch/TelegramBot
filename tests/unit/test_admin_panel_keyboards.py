"""Unit tests for admin-panel keyboard builders (Sprint 9.6, F-2/EP-22)."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.callbacks.factory import CallbackSigner, ParsedPanel
from bot.keyboards.admin_panel import (
    build_confirm,
    build_main_menu,
    build_section_menu,
    build_setting_stepper,
    build_settings_menu,
    nav_row,
)
from bot.panel.registry import SECTIONS, SETTING_FIELDS, is_write_action, setting_field
from domain.enums import UserRole


def _signer() -> CallbackSigner:
    return CallbackSigner("a-test-secret")


def _flat(markup: InlineKeyboardMarkup) -> list[InlineKeyboardButton]:
    return [b for row in markup.inline_keyboard for b in row]


def _parse(signer: CallbackSigner, button: InlineKeyboardButton) -> ParsedPanel:
    parsed = signer.unpack_panel(button.callback_data or "")
    assert parsed is not None  # every panel button must carry valid signed data
    return parsed


def _all_signed_and_within_limit(signer: CallbackSigner, markup: InlineKeyboardMarkup) -> None:
    for button in _flat(markup):
        assert len((button.callback_data or "").encode()) <= 64
        assert signer.unpack_panel(button.callback_data or "") is not None


# --- main menu ------------------------------------------------------------
def test_main_menu_owner_sees_all_sections() -> None:
    signer = _signer()
    markup = build_main_menu(UserRole.OWNER, signer)
    sections = {_parse(signer, b).section for b in _flat(markup)}
    assert sections == {s.code for s in SECTIONS}
    _all_signed_and_within_limit(signer, markup)


def test_main_menu_hides_owner_only_sections_from_moderator() -> None:
    signer = _signer()
    markup = build_main_menu(UserRole.MODERATOR, signer)
    sections = {_parse(signer, b).section for b in _flat(markup)}
    assert "b" not in sections  # Broadcast is owner_only
    assert sections == {s.code for s in SECTIONS if not s.owner_only}


def test_main_menu_buttons_open_sections() -> None:
    signer = _signer()
    for button in _flat(build_main_menu(UserRole.OWNER, signer)):
        assert _parse(signer, button).action == "op"


# --- section menu ---------------------------------------------------------
def test_section_menu_owner_sees_write_items() -> None:
    signer = _signer()
    markup = build_section_menu("u", UserRole.OWNER, signer)
    actions = {_parse(signer, b).action for b in _flat(markup)}
    assert {"ban", "ubn", "up", "rp", "mka", "rma"} <= actions  # write items present
    assert "hm" in actions  # Home in nav row


def test_section_menu_hides_write_items_from_moderator() -> None:
    signer = _signer()
    markup = build_section_menu("u", UserRole.MODERATOR, signer)
    actions = [_parse(signer, b).action for b in _flat(markup)]
    # Only read items + nav remain; no write-tier action is rendered.
    assert not any(a not in ("ls", "inf", "bk", "hm", "op") and is_write_action(a) for a in actions)
    assert "ls" in actions and "inf" in actions
    assert "ban" not in actions


def test_section_menu_has_back_and_home() -> None:
    signer = _signer()
    markup = build_section_menu("a", UserRole.OWNER, signer)
    nav = markup.inline_keyboard[-1]
    parsed = [_parse(signer, b) for b in nav]
    assert any(p.section == "mn" and p.action == "op" for p in parsed)  # Back -> main
    assert any(p.action == "hm" for p in parsed)  # Home


# --- settings menu + stepper ----------------------------------------------
def test_settings_menu_owner_lists_every_field() -> None:
    signer = _signer()
    markup = build_settings_menu(UserRole.OWNER, signer)
    edit_args = sorted(
        p.arg for b in _flat(markup) if (p := _parse(signer, b)).action == "e" and p.arg is not None
    )
    assert edit_args == [f.index for f in SETTING_FIELDS]


def test_settings_menu_moderator_has_no_edit_buttons() -> None:
    signer = _signer()
    markup = build_settings_menu(UserRole.MODERATOR, signer)
    actions = {_parse(signer, b).action for b in _flat(markup)}
    assert "e" not in actions  # no edit affordance
    assert "hm" in actions  # nav still present


def test_stepper_carries_clamped_values() -> None:
    signer = _signer()
    field = setting_field(0)  # worker_count: step 1, min 1, max 32
    assert field is not None
    markup = build_setting_stepper(field, 1, signer)  # at min
    by_action = {_parse(signer, b).action: _parse(signer, b) for b in _flat(markup)}
    assert by_action["-"].value == 1  # decrement clamped at min
    assert by_action["+"].value == 2
    assert by_action["sv"].value == 1  # Save carries the current candidate
    assert by_action["sv"].arg == 0


def test_stepper_clamps_at_max() -> None:
    signer = _signer()
    field = setting_field(0)
    assert field is not None
    markup = build_setting_stepper(field, 32, signer)
    by_action = {_parse(signer, b).action: _parse(signer, b) for b in _flat(markup)}
    assert by_action["+"].value == 32  # increment clamped at max
    assert by_action["-"].value == 31


def test_stepper_back_returns_to_settings_menu() -> None:
    signer = _signer()
    field = setting_field(3)
    assert field is not None
    nav = build_setting_stepper(field, 30, signer).inline_keyboard[-1]
    parsed = [_parse(signer, b) for b in nav]
    assert any(p.section == "s" and p.action == "op" for p in parsed)


# --- confirm + nav --------------------------------------------------------
def test_confirm_has_confirm_and_cancel() -> None:
    signer = _signer()
    markup = build_confirm(signer, confirm=("a", "dec", 7), cancel=("a", "op"))
    by_action = {_parse(signer, b).action: _parse(signer, b) for b in _flat(markup)}
    assert by_action["dec"].arg == 7  # confirm carries the target id
    assert "op" in by_action  # cancel routes back


def test_nav_row_includes_cancel_when_requested() -> None:
    signer = _signer()
    row = nav_row(signer, back=("s", "op"), cancel=("s", "cx"))
    actions = {_parse(signer, b).action for b in row}
    assert actions == {"op", "cx", "hm"}
