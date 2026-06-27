"""Security · Data Security (MASTER_PLAN §25.9.4).

Secrets must never reach logs, reprs, or the Sentry backend. The scrubber,
``Settings.__repr__``, and Sentry ``before_send`` all redact secret-looking keys.
"""

from __future__ import annotations

from pathlib import Path

from core.config import Settings
from core.constants import REDACTED, SECRET_KEY_SUBSTRINGS
from core.logging import SensitiveScrubber
from core.sentry import _before_send

ENV_EXAMPLE = str(Path(__file__).resolve().parents[3] / ".env.example")
_SENTINEL = "S3CR3T-sentinel-value-xyz"


# --- Structured-log scrubber ----------------------------------------------
def test_scrubber_redacts_secret_keys() -> None:
    scrubber = SensitiveScrubber()
    event = {
        "event": "login",
        "bot_token": _SENTINEL,
        "db_password": _SENTINEL,
        "authorization": _SENTINEL,
        "sentry_dsn": _SENTINEL,
        "user_id": 5,
    }
    out = scrubber(None, "info", event)
    assert out["bot_token"] == REDACTED
    assert out["db_password"] == REDACTED
    assert out["authorization"] == REDACTED
    assert out["sentry_dsn"] == REDACTED
    assert out["user_id"] == 5  # non-secret preserved
    assert _SENTINEL not in str(out)


def test_scrubber_redacts_nested_mappings() -> None:
    scrubber = SensitiveScrubber()
    event = {"event": "x", "ctx": {"api_key": _SENTINEL, "ok": "visible"}}
    out = scrubber(None, "info", event)
    assert out["ctx"]["api_key"] == REDACTED
    assert out["ctx"]["ok"] == "visible"


def test_secret_substring_catalog_is_comprehensive() -> None:
    for needle in ("secret", "token", "password", "dsn", "api_key", "authorization"):
        assert needle in SECRET_KEY_SUBSTRINGS


# --- Settings repr --------------------------------------------------------
def test_settings_repr_redacts_secrets() -> None:
    settings = Settings(_env_file=ENV_EXAMPLE)  # type: ignore[call-arg]
    rendered = repr(settings)
    # The shipped placeholders for secret fields must not be visible.
    assert settings.bot_token.get_secret_value() not in rendered
    assert settings.db_password.get_secret_value() not in rendered
    assert REDACTED in rendered


# --- Sentry before_send ---------------------------------------------------
def test_sentry_before_send_scrubs_event() -> None:
    event = {
        "message": "boom",
        "extra": {"bot_token": _SENTINEL, "note": "fine"},
        "tags": {"password": _SENTINEL},
    }
    scrubbed = _before_send(event, {})  # type: ignore[arg-type]
    assert scrubbed is not None
    assert scrubbed["extra"]["bot_token"] == REDACTED
    assert scrubbed["extra"]["note"] == "fine"
    assert scrubbed["tags"]["password"] == REDACTED
    assert _SENTINEL not in str(scrubbed)
