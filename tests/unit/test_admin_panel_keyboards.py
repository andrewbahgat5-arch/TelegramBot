"""Unit tests for admin-panel keyboard builders (Sprint 9.6, F-2/EP-22; Sprint 11.5 i18n)."""

from __future__ import annotations

import datetime
from types import SimpleNamespace

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.callbacks.factory import CallbackSigner, ParsedPanel
from bot.keyboards.admin_panel import (
    build_ad_detail,
    build_ad_list,
    build_confirm,
    build_main_menu,
    build_section_menu,
    build_setting_stepper,
    build_settings_menu,
    build_user_detail,
    build_user_list,
    nav_row,
)
from bot.panel.registry import SECTIONS, SETTING_FIELDS, is_write_action, setting_field
from domain.entities.user import UserSnapshot
from domain.enums import UserRole

_TODAY = datetime.date(2026, 6, 26)
_LOCALE = "en"


def _signer() -> CallbackSigner:
    return CallbackSigner("a-test-secret")


def _snap(
    tid: int = 555, *, role: UserRole = UserRole.USER, banned: bool = False, premium: bool = False
) -> UserSnapshot:
    return UserSnapshot(
        id=tid,
        telegram_id=tid,
        role=role,
        is_banned=banned,
        is_premium=premium,
        daily_download_count=0,
        daily_download_count_reset_date=_TODAY,
        total_downloads=0,
    )


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
    markup = build_main_menu(UserRole.OWNER, signer, _LOCALE)
    sections = {_parse(signer, b).section for b in _flat(markup)}
    assert sections == {s.code for s in SECTIONS}
    _all_signed_and_within_limit(signer, markup)


def test_main_menu_hides_owner_only_sections_from_moderator() -> None:
    signer = _signer()
    markup = build_main_menu(UserRole.MODERATOR, signer, _LOCALE)
    sections = {_parse(signer, b).section for b in _flat(markup)}
    assert "b" not in sections  # Broadcast is owner_only
    assert sections == {s.code for s in SECTIONS if not s.owner_only}


def test_main_menu_buttons_open_sections() -> None:
    signer = _signer()
    for button in _flat(build_main_menu(UserRole.OWNER, signer, _LOCALE)):
        assert _parse(signer, button).action == "op"


# --- section menu ---------------------------------------------------------
def test_section_menu_owner_sees_write_items() -> None:
    signer = _signer()
    markup = build_section_menu("u", UserRole.OWNER, signer, _LOCALE)
    actions = {_parse(signer, b).action for b in _flat(markup)}
    assert {"ban", "ubn", "up", "rp", "mka", "rma"} <= actions  # write items present
    assert "hm" in actions  # Home in nav row


def test_section_menu_hides_write_items_from_moderator() -> None:
    signer = _signer()
    markup = build_section_menu("u", UserRole.MODERATOR, signer, _LOCALE)
    actions = [_parse(signer, b).action for b in _flat(markup)]
    # Only read items + nav remain; no write-tier action is rendered.
    assert not any(a not in ("ls", "inf", "bk", "hm", "op") and is_write_action(a) for a in actions)
    assert "ls" in actions and "inf" in actions
    assert "ban" not in actions


def test_section_menu_has_back_and_home() -> None:
    signer = _signer()
    markup = build_section_menu("a", UserRole.OWNER, signer, _LOCALE)
    nav = markup.inline_keyboard[-1]
    parsed = [_parse(signer, b) for b in nav]
    assert any(p.section == "mn" and p.action == "op" for p in parsed)  # Back -> main
    assert any(p.action == "hm" for p in parsed)  # Home


# --- settings menu + stepper ----------------------------------------------
def test_settings_menu_owner_lists_every_field() -> None:
    signer = _signer()
    markup = build_settings_menu(UserRole.OWNER, signer, _LOCALE)
    edit_args = sorted(
        p.arg for b in _flat(markup) if (p := _parse(signer, b)).action == "e" and p.arg is not None
    )
    assert edit_args == [f.index for f in SETTING_FIELDS]


def test_settings_menu_moderator_has_no_edit_buttons() -> None:
    signer = _signer()
    markup = build_settings_menu(UserRole.MODERATOR, signer, _LOCALE)
    actions = {_parse(signer, b).action for b in _flat(markup)}
    assert "e" not in actions  # no edit affordance
    assert "hm" in actions  # nav still present


def test_stepper_carries_clamped_values() -> None:
    signer = _signer()
    field = setting_field(0)  # worker_count: step 1, min 1, max 32
    assert field is not None
    markup = build_setting_stepper(field, 1, signer, _LOCALE)  # at min
    by_action = {_parse(signer, b).action: _parse(signer, b) for b in _flat(markup)}
    assert by_action["-"].value == 1  # decrement clamped at min
    assert by_action["+"].value == 2
    assert by_action["sv"].value == 1  # Save carries the current candidate
    assert by_action["sv"].arg == 0


def test_stepper_clamps_at_max() -> None:
    signer = _signer()
    field = setting_field(0)
    assert field is not None
    markup = build_setting_stepper(field, 32, signer, _LOCALE)
    by_action = {_parse(signer, b).action: _parse(signer, b) for b in _flat(markup)}
    assert by_action["+"].value == 32  # increment clamped at max
    assert by_action["-"].value == 31


def test_stepper_back_returns_to_settings_menu() -> None:
    signer = _signer()
    field = setting_field(3)
    assert field is not None
    nav = build_setting_stepper(field, 30, signer, _LOCALE).inline_keyboard[-1]
    parsed = [_parse(signer, b) for b in nav]
    assert any(p.section == "s" and p.action == "op" for p in parsed)


# --- confirm + nav --------------------------------------------------------
def test_confirm_has_confirm_and_cancel() -> None:
    signer = _signer()
    markup = build_confirm(
        signer, _LOCALE, confirm=("u", "banc", 7, None), cancel=("u", "inf", 7)
    )
    by_action = {_parse(signer, b).action: _parse(signer, b) for b in _flat(markup)}
    assert by_action["banc"].arg == 7  # confirm carries the target id
    assert by_action["inf"].arg == 7  # cancel routes back to that user's detail


def test_confirm_carries_value_for_settings_save() -> None:
    signer = _signer()
    markup = build_confirm(signer, _LOCALE, confirm=("s", "sv", 0, 20), cancel=("s", "e", 0))
    save = next(p for b in _flat(markup) if (p := _parse(signer, b)).action == "sv")
    assert save.arg == 0 and save.value == 20  # typed value rides on the confirm button


def test_stepper_has_enter_value_button() -> None:
    signer = _signer()
    field = setting_field(0)
    assert field is not None
    actions = {
        _parse(signer, b).action for b in _flat(build_setting_stepper(field, 3, signer, _LOCALE))
    }
    assert "ev" in actions  # Enter Value alongside the minus/plus/save controls


def test_nav_row_includes_cancel_when_requested() -> None:
    signer = _signer()
    row = nav_row(signer, _LOCALE, back=("s", "op"), cancel=("s", "cx"))
    actions = {_parse(signer, b).action for b in row}
    assert actions == {"op", "cx", "hm"}


# --- user list + detail ---------------------------------------------------
def test_user_list_rows_open_details() -> None:
    signer = _signer()
    markup = build_user_list([_snap(111), _snap(222)], signer, _LOCALE)
    opened = {p.arg for b in _flat(markup) if (p := _parse(signer, b)).action == "inf"}
    assert opened == {111, 222}  # each row carries its telegram id
    _all_signed_and_within_limit(signer, markup)


def test_user_detail_owner_sees_contextual_actions() -> None:
    signer = _signer()
    markup = build_user_detail(
        _snap(banned=True, premium=True), UserRole.OWNER, signer, _LOCALE
    )
    actions = {_parse(signer, b).action for b in _flat(markup)}
    assert "ubn" in actions  # banned -> offer Unban (not Ban)
    assert "rp" in actions  # premium -> offer Remove Premium
    assert "mka" in actions  # plain user -> offer Make Admin
    assert "ban" not in actions and "up" not in actions


def test_user_detail_moderator_sees_no_actions() -> None:
    signer = _signer()
    markup = build_user_detail(_snap(), UserRole.MODERATOR, signer, _LOCALE)
    actions = {_parse(signer, b).action for b in _flat(markup)}
    assert actions == {"ls", "hm"}  # only the nav row (Back to list + Home)


def test_user_detail_no_actions_against_owner_target() -> None:
    signer = _signer()
    markup = build_user_detail(_snap(role=UserRole.OWNER), UserRole.OWNER, signer, _LOCALE)
    actions = {_parse(signer, b).action for b in _flat(markup)}
    assert actions == {"ls", "hm"}  # an owner can't be banned/demoted via the panel


# --- ad list + detail -----------------------------------------------------
def _ad(ad_id: int = 1, *, is_active: bool = True) -> SimpleNamespace:
    return SimpleNamespace(id=ad_id, title="Promo", is_active=is_active)


def test_ad_list_rows_open_details() -> None:
    signer = _signer()
    markup = build_ad_list([_ad(11), _ad(22)], signer, _LOCALE)
    opened = {p.arg for b in _flat(markup) if (p := _parse(signer, b)).action == "inf"}
    assert opened == {11, 22}


def test_ad_detail_owner_sees_actions() -> None:
    signer = _signer()
    actions = {
        _parse(signer, b).action
        for b in _flat(build_ad_detail(_ad(), UserRole.OWNER, signer, _LOCALE))
    }
    assert {"di", "bc", "de"} <= actions  # active ad → Disable + Broadcast + Delete


def test_ad_detail_moderator_sees_no_actions() -> None:
    signer = _signer()
    actions = {
        _parse(signer, b).action
        for b in _flat(build_ad_detail(_ad(), UserRole.MODERATOR, signer, _LOCALE))
    }
    assert actions == {"ls", "hm"}  # only the nav row
