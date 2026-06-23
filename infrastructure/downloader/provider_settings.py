"""Provider settings adapter (MASTER_PLAN 12.6.7, Task 5.2 support).

Implements the domain ``ProviderSettingsProtocol`` the ``DownloaderRegistry``
(a long-lived singleton) depends on. Because the registry outlives any single
request, this adapter opens a short-lived read session per lookup rather than
borrowing a request session. Reads are infrequent — the registry runs only on a
metadata-cache miss — so a small per-read query is acceptable for V1.

Lives in infrastructure (it uses ``SettingsRepository``); the registry depends only
on the domain protocol, keeping the layering intact (Section 8).
"""

from __future__ import annotations

import orjson
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from infrastructure.database.repositories.setting import SettingsRepository

# Section 13.4 defaults, used when a key is somehow absent from the seeded table.
_DEFAULTS: dict[str, str] = {
    "providers_enabled": '{"ytdlp": true}',
    "provider_priority_overrides": "{}",
    "provider_failover_enabled": "true",
    "provider_cooldown_seconds": "60",
    "provider_failure_threshold": "3",
}
_TRUE = frozenset({"true", "1", "yes", "on"})


class ProviderSettingsAdapter:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def _raw(self, key: str) -> str:
        async with self._session_factory() as session:
            row = await SettingsRepository(session).get_by_key(key)
        return row.value if row is not None else _DEFAULTS[key]

    async def providers_enabled(self) -> dict[str, bool]:
        value: dict[str, bool] = orjson.loads(await self._raw("providers_enabled"))
        return value

    async def priority_overrides(self) -> dict[str, int]:
        value: dict[str, int] = orjson.loads(await self._raw("provider_priority_overrides"))
        return value

    async def failover_enabled(self) -> bool:
        return (await self._raw("provider_failover_enabled")).strip().lower() in _TRUE

    async def cooldown_seconds(self) -> int:
        return int(await self._raw("provider_cooldown_seconds"))

    async def failure_threshold(self) -> int:
        return int(await self._raw("provider_failure_threshold"))
