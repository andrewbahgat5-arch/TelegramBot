"""Unit tests for the Bot factory's local-vs-public API selection (D-040, #12)."""

from __future__ import annotations

from pydantic import SecretStr

from infrastructure.telegram.client import build_bot
from tests.unit._fakes import load_settings

# aiogram validates the token shape (<digits>:<rest>) when constructing a Bot.
_FAKE_TOKEN = SecretStr("123456:test-token-AA")


async def test_build_bot_targets_local_api_when_configured() -> None:
    settings = load_settings()
    settings.bot_token = _FAKE_TOKEN
    settings.bot_api_base_url = "http://localhost:8081"
    bot = build_bot(settings)
    try:
        assert "localhost:8081" in bot.session.api.base
    finally:
        await bot.session.close()


async def test_build_bot_defaults_to_public_api() -> None:
    settings = load_settings()  # .env.example leaves BOT_API_BASE_URL empty
    settings.bot_token = _FAKE_TOKEN
    assert settings.use_local_bot_api is False
    bot = build_bot(settings)
    try:
        assert "api.telegram.org" in bot.session.api.base
    finally:
        await bot.session.close()


async def test_build_bot_uses_job_budget_as_request_timeout() -> None:
    # Uploads must not die on aiogram's 60 s default; the session timeout is the per-job
    # budget so a slow large-file upload completes instead of timing out + retrying.
    settings = load_settings()
    settings.bot_token = _FAKE_TOKEN
    settings.worker_job_timeout = 300
    bot = build_bot(settings)
    try:
        assert bot.session.timeout == 300.0
    finally:
        await bot.session.close()


async def test_build_bot_sets_timeout_for_local_api_too() -> None:
    settings = load_settings()
    settings.bot_token = _FAKE_TOKEN
    settings.bot_api_base_url = "http://localhost:8081"
    settings.worker_job_timeout = 300
    bot = build_bot(settings)
    try:
        assert bot.session.timeout == 300.0
        assert "localhost:8081" in bot.session.api.base
    finally:
        await bot.session.close()
