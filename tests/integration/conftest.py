"""Integration-test fixtures (MASTER_PLAN Task 2.9).

Each test runs inside a transaction that is rolled back afterwards, so the
database is never mutated permanently. The suite skips automatically when Postgres
is unavailable or the schema has not been migrated, so unit-only runs do not fail.

The schema must already be migrated (``alembic upgrade head``); CI applies it as a
job step. DB connection settings come from ``.env.example`` (which matches the
local docker-compose stack) and may be overridden by environment variables.
"""

from __future__ import annotations

import random
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from core.config import Settings
from infrastructure.database.engine import create_engine
from infrastructure.redis.client import RedisClients, create_redis_clients

ENV_EXAMPLE = str(Path(__file__).resolve().parents[2] / ".env.example")


def _settings() -> Settings:
    return Settings(_env_file=ENV_EXAMPLE)  # type: ignore[call-arg]


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_engine(_settings())
    try:
        async with eng.connect() as conn:
            # Verify connectivity and that the schema has been migrated.
            await conn.execute(text("SELECT 1 FROM settings LIMIT 1"))
    except Exception:  # any failure means "no usable DB" -> skip the suite
        await eng.dispose()
        pytest.skip("Postgres/migrated schema not available for integration tests")
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as conn:
        txn = await conn.begin()
        session = AsyncSession(
            bind=conn,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            await txn.rollback()


@pytest.fixture
def telegram_id() -> int:
    """A random Telegram id, avoiding collisions with seeded/owner rows."""
    return random.randint(1_000_000_000, 9_999_999_999)  # noqa: S311 - test data, not crypto


@pytest_asyncio.fixture
async def redis_clients() -> AsyncIterator[RedisClients]:
    clients = create_redis_clients(_settings())
    try:
        await clients.cache.ping()
    except Exception:  # Redis not running -> skip the Redis suites
        await clients.aclose()
        pytest.skip("Redis not available for integration tests")
    # Isolate each test: start and end with empty cache/queue databases.
    await clients.cache.flushdb()
    await clients.queue.flushdb()
    yield clients
    await clients.cache.flushdb()
    await clients.queue.flushdb()
    await clients.aclose()
