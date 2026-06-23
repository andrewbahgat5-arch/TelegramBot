"""Async session factory (MASTER_PLAN Task 2.4).

The session lifecycle is owned by the caller (e.g. ``DbSessionMiddleware`` opens a
session per Telegram update and commits/rolls back). Repositories never commit;
they ``add``/``flush`` only, so the unit of work is controlled at the entry point.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Build an ``AsyncSession`` factory bound to ``engine``."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
