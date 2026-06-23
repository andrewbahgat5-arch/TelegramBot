"""Unit tests for core/constants.py (MASTER_PLAN 12.2, 14.3)."""

from __future__ import annotations

from core import constants


def test_priority_bands_ordered() -> None:
    assert (
        constants.PRIORITY_URGENT
        < constants.PRIORITY_HIGH
        < constants.PRIORITY_NORMAL
        < constants.PRIORITY_LOW
    )


def test_priority_score_formula() -> None:
    # score = base + (unix_time_ms / 1000)
    assert constants.priority_score(constants.PRIORITY_NORMAL, 2000) == 1002.0
    assert constants.priority_score(0, 0) == 0.0


def test_priority_score_preserves_band_separation() -> None:
    # A normal job is always behind an urgent job issued at the same instant.
    now_ms = 1_700_000_000_000
    urgent = constants.priority_score(constants.PRIORITY_URGENT, now_ms)
    normal = constants.priority_score(constants.PRIORITY_NORMAL, now_ms)
    assert urgent < normal


def test_secret_substrings_cover_known_secrets() -> None:
    assert "token" in constants.SECRET_KEY_SUBSTRINGS
    assert "password" in constants.SECRET_KEY_SUBSTRINGS
    assert "dsn" in constants.SECRET_KEY_SUBSTRINGS


def test_secret_env_keys_match_section_13_2() -> None:
    assert set(constants.SECRET_ENV_KEYS) == {
        "BOT_TOKEN",
        "BOT_WEBHOOK_SECRET",
        "DB_PASSWORD",
        "SENTRY_DSN",
    }
