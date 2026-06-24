"""BroadcastRepository (MASTER_PLAN 10.9, flow 16.8)."""

from __future__ import annotations

import datetime

from sqlalchemy import select, update

from infrastructure.database.models import Broadcast
from infrastructure.database.repositories.base import SqlAlchemyRepository


class BroadcastRepository(SqlAlchemyRepository[Broadcast]):
    model = Broadcast

    async def create_pending(
        self,
        *,
        created_by: int,
        message_text: str,
        target_language: str | None,
        target_role: str | None,
        expected_total: int,
    ) -> Broadcast:
        """Insert a ``pending`` broadcast the worker will pick up (16.8 step 1)."""
        broadcast = Broadcast(
            created_by=created_by,
            message_text=message_text,
            target_language=target_language,
            target_role=target_role,
            expected_total=expected_total,
            status="pending",
        )
        return await self.add(broadcast)

    async def get_next_pending(self) -> Broadcast | None:
        """Oldest ``pending`` broadcast, FIFO by id (16.8 step 1)."""
        result = await self.session.execute(
            select(Broadcast)
            .where(Broadcast.status == "pending")
            .order_by(Broadcast.id.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def set_status(
        self, broadcast_id: int, status: str, *, completed_at: datetime.datetime | None = None
    ) -> None:
        values: dict[str, object] = {"status": status}
        if completed_at is not None:
            values["completed_at"] = completed_at
        await self.session.execute(
            update(Broadcast).where(Broadcast.id == broadcast_id).values(**values)
        )
        await self.session.flush()

    async def add_counts(self, broadcast_id: int, *, sent: int, failed: int) -> None:
        """Atomic per-chunk counter bump so progress survives a worker crash (16.8 step 4)."""
        await self.session.execute(
            update(Broadcast)
            .where(Broadcast.id == broadcast_id)
            .values(
                total_sent=Broadcast.total_sent + sent,
                total_failed=Broadcast.total_failed + failed,
            )
        )
        await self.session.flush()
