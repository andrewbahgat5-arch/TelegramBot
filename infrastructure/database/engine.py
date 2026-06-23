"""Async SQLAlchemy engine construction (MASTER_PLAN Task 2.4).

Builds the connection URL from ``core/config.py`` and creates an ``AsyncEngine``.
``statement_cache_size=0`` is required because PgBouncer runs in transaction
pooling mode (D-020), which is incompatible with asyncpg's prepared-statement
cache.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from core.config import Settings


def build_url(settings: Settings) -> URL:
    """Construct the async Postgres URL, escaping credentials safely."""
    return URL.create(
        drivername="postgresql+asyncpg",
        username=settings.db_user,
        password=settings.db_password.get_secret_value(),
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
    )


def create_engine(settings: Settings) -> AsyncEngine:
    """Create the application's async engine."""
    connect_args: dict[str, Any] = {"statement_cache_size": 0}
    if settings.db_ssl:
        connect_args["ssl"] = True

    return create_async_engine(
        build_url(settings),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        connect_args=connect_args,
    )
