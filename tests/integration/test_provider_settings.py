"""Integration tests for ProviderSettingsAdapter (MASTER_PLAN 12.6.7).

Reads the seeded provider settings from the live database through the adapter the
registry depends on. Auto-skips when Postgres/migrated schema is unavailable.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from infrastructure.database.session import create_session_factory
from infrastructure.downloader.provider_settings import ProviderSettingsAdapter

pytestmark = pytest.mark.asyncio


def _adapter(engine: AsyncEngine) -> ProviderSettingsAdapter:
    return ProviderSettingsAdapter(create_session_factory(engine))


async def test_reads_seeded_provider_settings(engine: AsyncEngine) -> None:
    adapter = _adapter(engine)
    assert await adapter.providers_enabled() == {"ytdlp": True}
    assert await adapter.priority_overrides() == {}
    assert await adapter.failover_enabled() is True
    assert await adapter.cooldown_seconds() == 60
    assert await adapter.failure_threshold() == 3
