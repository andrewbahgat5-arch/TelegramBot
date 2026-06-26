"""AdEventRepository (MASTER_PLAN 10.16, Sprint 9.5.9, partitioned).

Writes per-event ad analytics rows and reads simple aggregates. Writes happen off the
delivery hot path (via ``AdEventRecorder``, D-052); the read helpers back per-ad /
per-placement reporting.
"""

from __future__ import annotations

from sqlalchemy import func, select

from infrastructure.database.models import AdEvent
from infrastructure.database.repositories.base import SqlAlchemyRepository


class AdEventRepository(SqlAlchemyRepository[AdEvent]):
    model = AdEvent

    async def record(
        self,
        *,
        event_type: str,
        advertisement_id: int,
        user_id: int | None = None,
        placement: str | None = None,
        button_id: int | None = None,
    ) -> AdEvent:
        """Insert one ad event row (impression/click)."""
        return await self.add(
            AdEvent(
                event_type=event_type,
                advertisement_id=advertisement_id,
                user_id=user_id,
                placement=placement,
                button_id=button_id,
            )
        )

    async def count_for_ad(self, advertisement_id: int, *, event_type: str | None = None) -> int:
        """Count events for one ad, optionally restricted to an ``event_type``."""
        conditions = [AdEvent.advertisement_id == advertisement_id]
        if event_type is not None:
            conditions.append(AdEvent.event_type == event_type)
        result = await self.session.execute(
            select(func.count()).select_from(AdEvent).where(*conditions)
        )
        return int(result.scalar_one())
