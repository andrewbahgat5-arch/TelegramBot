"""Alembic environment (MASTER_PLAN Task 2.1).

Runs migrations against the async engine built from ``core/config.py``. Logging is
intentionally not configured here — the app owns structlog setup (Section 4.2.2).
"""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy import Connection

from core.config import Settings
from infrastructure.database.engine import create_engine
from infrastructure.database.models import Base

config = context.config
target_metadata = Base.metadata


def _do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    engine = create_engine(Settings())  # type: ignore[call-arg]
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_do_run_migrations)
    finally:
        await engine.dispose()


def run_migrations_offline() -> None:
    settings = Settings()  # type: ignore[call-arg]
    from infrastructure.database.engine import build_url

    context.configure(
        url=build_url(settings).render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
