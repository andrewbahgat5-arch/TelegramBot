"""Unit tests for core/config.py (MASTER_PLAN Task 1.1, 13.2, 14.3)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from core.config import Settings
from core.constants import REDACTED

_REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = str(_REPO_ROOT / ".env.example")
ENV_PRODUCTION_EXAMPLE = str(_REPO_ROOT / ".env.production.example")


def _env_keys(path: str) -> set[str]:
    """Collect the ``KEY`` names from a dotenv file (ignoring comments/blanks)."""
    keys: set[str] = set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        keys.add(stripped.split("=", 1)[0].strip())
    return keys


def _settings() -> Settings:
    return Settings(_env_file=ENV_EXAMPLE)  # type: ignore[call-arg]


def test_builds_from_env_example() -> None:
    settings = _settings()
    assert settings.bot_token.get_secret_value() == "bot-token-test-XXXX"
    assert settings.db_port == 5432
    assert settings.db_host == "localhost"
    assert settings.log_format == "json"
    assert settings.worker_count == 3
    assert settings.telegram_alerts_chat_id is None


def test_production_example_builds_and_has_production_defaults() -> None:
    """`.env.production.example` (Sprint 12 A2) parses into a valid Settings.

    It carries production-appropriate defaults and must not trip the environment
    safety rules (the test-env guard is a no-op under DEPLOY_ENV=production).
    """
    settings = Settings(_env_file=ENV_PRODUCTION_EXAMPLE)  # type: ignore[call-arg]
    assert settings.deploy_env == "production"
    assert settings.is_production is True
    assert settings.sentry_environment == "production"
    assert settings.log_format == "json"
    assert settings.log_level == "INFO"
    # The DB path is the pooler (compose additionally forces it, D-020).
    assert settings.db_host == "pgbouncer"
    assert settings.db_port == 6432
    # Admin HTTP API is not served in V1 → no key shipped in the example.
    assert settings.admin_api_enabled is False


def test_production_example_key_set_matches_locked_set() -> None:
    """The production example must define exactly the LOCKED §13.2 key set.

    Parity with `.env.example` keeps the two files from drifting: a new env var
    added to one but not the other fails this test.
    """
    assert _env_keys(ENV_PRODUCTION_EXAMPLE) == _env_keys(ENV_EXAMPLE)


def test_production_example_contains_no_real_secrets() -> None:
    """Secrets in the example are placeholders, never real values (A2 rule)."""
    text = Path(ENV_PRODUCTION_EXAMPLE).read_text(encoding="utf-8")
    for secret_key in ("SENTRY_DSN", "ADMIN_API_KEY", "BOT_WEBHOOK_SECRET"):
        # These are empty in the example (disabled/optional surfaces).
        assert f"{secret_key}=\n" in text or text.rstrip().endswith(f"{secret_key}=")
    # The must-be-set secrets carry an obvious placeholder sentinel, not a value.
    assert "BOT_TOKEN=__SET_IN_SECRET_BACKEND__" in text
    assert "DB_PASSWORD=__SET_IN_SECRET_BACKEND__" in text


def test_repr_redacts_secrets() -> None:
    settings = _settings()
    rendered = repr(settings)
    assert "bot-token-test-XXXX" not in rendered
    assert "change-me-local" not in rendered  # db_password placeholder
    assert REDACTED in rendered
    # Non-secret fields remain visible.
    assert "db_host=" in rendered
    assert "localhost" in rendered
    # str() is the same safe representation.
    assert str(settings) == rendered


def test_secret_value_not_in_str() -> None:
    settings = _settings()
    assert settings.db_password.get_secret_value() == "change-me-local"
    assert "change-me-local" not in str(settings)


def test_admin_api_disabled_when_key_empty() -> None:
    settings = _settings()
    assert settings.admin_api_enabled is False
    assert settings.admin_api_key.get_secret_value() == ""


def test_admin_api_enabled_with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_API_KEY", "super-secret-admin-key")
    settings = _settings()
    assert settings.admin_api_enabled is True
    assert settings.admin_api_key.get_secret_value() == "super-secret-admin-key"
    # The key is a secret: it never appears in the safe representation (Section 14.3).
    assert "super-secret-admin-key" not in repr(settings)


def test_sentry_disabled_when_dsn_empty() -> None:
    assert _settings().sentry_enabled is False


def test_sentry_enabled_with_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTRY_DSN", "https://abc@o0.ingest.sentry.io/1")
    assert _settings().sentry_enabled is True


def test_use_webhook_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _settings().use_webhook is False
    monkeypatch.setenv("BOT_WEBHOOK_URL", "https://example.com/hook")
    monkeypatch.setenv("BOT_WEBHOOK_SECRET", "s3cr3t")
    assert _settings().use_webhook is True


def test_invalid_log_level_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "LOUD")
    with pytest.raises(ValidationError):
        _settings()


def test_sample_rate_out_of_range_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "2.0")
    with pytest.raises(ValidationError):
        _settings()


def test_webhook_secret_required_in_webhook_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOT_WEBHOOK_URL", "https://example.com/hook")
    monkeypatch.setenv("BOT_WEBHOOK_SECRET", "")
    with pytest.raises(ValidationError):
        _settings()


def test_deploy_env_defaults_to_development() -> None:
    settings = _settings()
    assert settings.deploy_env == "development"
    assert settings.is_test_env is False
    assert settings.is_production is False


def test_deploy_env_normalized_to_lowercase(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOY_ENV", "  TEST ")
    settings = _settings()
    assert settings.deploy_env == "test"
    assert settings.is_test_env is True


def test_deploy_env_production_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOY_ENV", "production")
    settings = _settings()
    assert settings.is_production is True
    assert settings.is_test_env is False


def test_invalid_deploy_env_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOY_ENV", "staging")
    with pytest.raises(ValidationError):
        _settings()


def test_prod_fingerprint_defaults_empty() -> None:
    assert _settings().prod_bot_token_fingerprint == ""


def test_missing_required_field_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # No env file and no env vars -> required fields are missing.
    for key in (
        "BOT_TOKEN",
        "BOT_OWNER_TELEGRAM_ID",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
        "REDIS_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]
