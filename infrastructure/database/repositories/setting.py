"""SettingsRepository (MASTER_PLAN 10.11)."""

from __future__ import annotations

import datetime
from collections.abc import Sequence

from sqlalchemy import select

from infrastructure.database.models import Setting
from infrastructure.database.repositories.base import SqlAlchemyRepository


class SettingsRepository(SqlAlchemyRepository[Setting]):
    model = Setting
    id_attr = "key"

    async def get_by_key(self, key: str) -> Setting | None:
        result = await self.session.execute(select(Setting).where(Setting.key == key))
        return result.scalar_one_or_none()

    async def list_all(self) -> Sequence[Setting]:
        """Every settings row, ordered by key (admin ``/settings`` listing)."""
        result = await self.session.execute(select(Setting).order_by(Setting.key.asc()))
        return result.scalars().all()

    async def upsert(self, key: str, value: str, *, updated_by: int | None = None) -> Setting:
        """Update a setting's value, or create it (default ``string`` type) if absent.

        Done at the ORM level so any already-loaded instance reflects the new value
        (a raw INSERT...ON CONFLICT...RETURNING would return the stale identity-mapped
        row). Records ``updated_at``/``updated_by`` (Section 13.5).
        """
        setting = await self.get_by_key(key)
        if setting is None:
            return await self.add(
                Setting(key=key, value=value, value_type="string", updated_by=updated_by)
            )
        setting.value = value
        setting.updated_at = datetime.datetime.now(datetime.UTC)
        if updated_by is not None:
            setting.updated_by = updated_by
        await self.session.flush()
        return setting
