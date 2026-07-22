"""Unit tests for the entitlement registry (VERSION_2_MASTER_PLAN §5.2, V2.1)."""

from __future__ import annotations

import pytest

from domain.entitlements import (
    EntitlementError,
    ResolvedEntitlements,
    validate,
)

_VALID: dict[str, object] = {
    "daily_download_limit": 10,
    "cooldown_seconds": 30,
    "max_file_size_bytes": 52_428_800,
    "ad_free": False,
    "playlists_enabled": False,
}


def test_valid_entitlements_pass() -> None:
    validate("free", _VALID)  # must not raise


def test_unknown_key_rejected() -> None:
    bad = _VALID | {"surprise": 1}
    with pytest.raises(EntitlementError, match="unknown entitlement key"):
        validate("free", bad)


def test_missing_key_rejected() -> None:
    bad = {k: v for k, v in _VALID.items() if k != "cooldown_seconds"}
    with pytest.raises(EntitlementError, match="missing entitlement key 'cooldown_seconds'"):
        validate("free", bad)


def test_wrong_type_rejected() -> None:
    bad = _VALID | {"daily_download_limit": "10"}  # string, not int
    with pytest.raises(EntitlementError, match="must be int"):
        validate("free", bad)


def test_bool_does_not_satisfy_int_key() -> None:
    # bool is an int subclass in Python — the registry must not accept True for an int key.
    bad = _VALID | {"daily_download_limit": True}
    with pytest.raises(EntitlementError, match="must be int"):
        validate("free", bad)


def test_int_does_not_satisfy_bool_key() -> None:
    bad = _VALID | {"ad_free": 1}  # int, not bool
    with pytest.raises(EntitlementError, match="must be bool"):
        validate("free", bad)


def test_resolved_entitlements_from_mapping() -> None:
    resolved = ResolvedEntitlements.from_mapping(_VALID)
    assert resolved.daily_download_limit == 10
    assert resolved.cooldown_seconds == 30
    assert resolved.max_file_size_bytes == 52_428_800
    assert resolved.ad_free is False
    assert resolved.playlists_enabled is False
