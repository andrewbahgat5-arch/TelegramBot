"""Unit tests for the panel action registry + PanelFilter (Sprint 9.6, F-2/EP-22)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from aiogram.types import CallbackQuery, Message

from bot.callbacks.factory import CallbackSigner, ParsedPanel
from bot.filters.panel_filter import PanelFilter
from bot.panel.registry import READ_ACTIONS, is_write_action


def _signer() -> CallbackSigner:
    return CallbackSigner("a-test-secret")


def _cb(data: str) -> Any:
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = data
    return callback


# --- registry -------------------------------------------------------------
def test_read_actions_are_not_write() -> None:
    for action in READ_ACTIONS:
        assert is_write_action(action) is False


def test_mutating_and_unknown_actions_are_write() -> None:
    assert is_write_action("sv") is True  # save a setting
    assert is_write_action("de") is True  # open delete-confirm (leads to a mutation)
    assert is_write_action("ban") is True
    assert is_write_action("zzz-never-registered") is True  # fail-safe default


# --- filter: tier matching ------------------------------------------------
async def test_read_callback_matches_read_filter_and_injects_panel() -> None:
    signer = _signer()
    result = await PanelFilter(mutating=False)(
        _cb(signer.pack_panel("u", "inf", arg=555)), callback_signer=signer
    )
    assert isinstance(result, dict)
    panel = result["panel"]
    assert isinstance(panel, ParsedPanel)
    assert panel.section == "u"
    assert panel.action == "inf"
    assert panel.arg == 555


async def test_read_callback_does_not_match_write_filter() -> None:
    signer = _signer()
    result = await PanelFilter(mutating=True)(
        _cb(signer.pack_panel("mn", "op")), callback_signer=signer
    )
    assert result is False


async def test_write_callback_matches_write_filter_and_injects_panel() -> None:
    signer = _signer()
    result = await PanelFilter(mutating=True)(
        _cb(signer.pack_panel("s", "sv", arg=3, value=15)), callback_signer=signer
    )
    assert isinstance(result, dict)
    assert result["panel"].action == "sv"
    assert result["panel"].value == 15


async def test_write_callback_does_not_match_read_filter() -> None:
    signer = _signer()
    result = await PanelFilter(mutating=False)(
        _cb(signer.pack_panel("a", "de", arg=42)), callback_signer=signer
    )
    assert result is False


# --- filter: rejection paths ----------------------------------------------
async def test_forged_signature_never_matches() -> None:
    signer = _signer()
    forged = signer.pack_panel("a", "de", arg=42).replace("42", "43", 1)
    assert await PanelFilter(mutating=True)(_cb(forged), callback_signer=signer) is False
    assert await PanelFilter(mutating=False)(_cb(forged), callback_signer=signer) is False


async def test_wrong_key_never_matches() -> None:
    data = CallbackSigner("key-one").pack_panel("s", "sv", arg=1, value=2)
    other = CallbackSigner("key-two")
    assert await PanelFilter(mutating=True)(_cb(data), callback_signer=other) is False


async def test_non_panel_data_does_not_match() -> None:
    signer = _signer()
    # A well-formed media callback (different namespace) must not match the panel.
    assert await PanelFilter(mutating=False)(_cb("h|2|deadbeef00"), callback_signer=signer) is False
    assert await PanelFilter(mutating=False)(_cb(""), callback_signer=signer) is False


async def test_non_callback_event_does_not_match() -> None:
    signer = _signer()
    message = AsyncMock(spec=Message)
    assert await PanelFilter(mutating=False)(message, callback_signer=signer) is False
