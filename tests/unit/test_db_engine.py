"""Unit tests for engine/session builders (MASTER_PLAN Task 2.4)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from core.config import Settings
from infrastructure.database.engine import build_url, create_engine
from infrastructure.database.session import create_session_factory

ENV_EXAMPLE = str(Path(__file__).resolve().parents[2] / ".env.example")


def _settings() -> Settings:
    return Settings(_env_file=ENV_EXAMPLE)  # type: ignore[call-arg]


def test_build_url_uses_asyncpg_driver() -> None:
    url = build_url(_settings())
    assert url.drivername == "postgresql+asyncpg"
    assert url.host == "localhost"
    assert url.database == "telegram_bot"
    assert url.username == "telegram_bot"
    # Password is carried but not rendered unless explicitly requested.
    assert url.password == "change-me-local"


def test_create_engine_and_session_factory() -> None:
    # create_async_engine does not open a connection, so this is safe without a DB.
    engine = create_engine(_settings())
    assert isinstance(engine, AsyncEngine)
    factory = create_session_factory(engine)
    assert isinstance(factory, async_sessionmaker)
