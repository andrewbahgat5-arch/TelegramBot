"""BroadcastRepository (MASTER_PLAN 10.9, flow 16.8)."""

from __future__ import annotations

import datetime
from collections.abc import Sequence

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, or_, select, update

from infrastructure.database.models import Broadcast
from infrastructure.database.repositories.base import SqlAlchemyRepository


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


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
        advertisement_id: int | None = None,
        scheduled_at: datetime.datetime | None = None,
        audience_expression_id: int | None = None,
        status: str = "pending",
    ) -> Broadcast:
        """Insert a broadcast the worker will pick up once ``pending`` (16.8 step 1).

        ``advertisement_id`` (Sprint 9.5) links an ad to deliver via copyMessage instead
        of plain ``message_text``. ``scheduled_at`` (9.5.10) defers delivery: NULL = send
        as soon as the worker polls; set → the due-poller skips it until it is due.
        ``audience_expression_id`` (Sprint 9.6, D-055) targets a unified audience
        expression; NULL = legacy ``target_role`` / ``target_language``. ``status``
        (Publish-vs-Save wizard flow) is ``pending`` (queued for the worker) or ``draft``
        (saved but not sent — :meth:`set_status` moves it to ``pending`` on Publish).
        """
        broadcast = Broadcast(
            created_by=created_by,
            message_text=message_text,
            target_language=target_language,
            target_role=target_role,
            expected_total=expected_total,
            advertisement_id=advertisement_id,
            scheduled_at=scheduled_at,
            audience_expression_id=audience_expression_id,
            status=status,
        )
        return await self.add(broadcast)

    async def list_all(self) -> Sequence[Broadcast]:
        """Every saved broadcast (draft + pending + completed), newest first (Save/Publish flow)."""
        result = await self.session.execute(select(Broadcast).order_by(Broadcast.id.desc()))
        return result.scalars().all()

    async def list_by_language(
        self, language: str | None, *, limit: int, offset: int
    ) -> Sequence[Broadcast]:
        clause = (
            Broadcast.target_language.is_(None)
            if language is None
            else Broadcast.target_language == language
        )
        result = await self.session.execute(
            select(Broadcast).where(clause).order_by(Broadcast.id.desc()).limit(limit).offset(offset)
        )
        return result.scalars().all()

    async def count_by_language(self, language: str | None) -> int:
        clause = (
            Broadcast.target_language.is_(None)
            if language is None
            else Broadcast.target_language == language
        )
        result = await self.session.execute(
            select(func.count()).select_from(Broadcast).where(clause)
        )
        return result.scalar_one()

    async def delete_broadcast(self, broadcast_id: int) -> bool:
        result = await self.session.execute(
            sa_delete(Broadcast).where(Broadcast.id == broadcast_id)
        )
        await self.session.flush()
        return (result.rowcount or 0) > 0

    async def broadcast_totals_for_ad(
        self, ad_id: int
    ) -> tuple[int, datetime.datetime | None]:
        """Total sends and last completion for broadcasts linked to an ad (Phase 4)."""
        result = await self.session.execute(
            select(
                func.coalesce(func.sum(Broadcast.total_sent), 0),
                func.max(Broadcast.completed_at),
            ).where(Broadcast.advertisement_id == ad_id)
        )
        row = result.one()
        return int(row[0]), row[1]

    async def get_next_pending(self, *, now: datetime.datetime | None = None) -> Broadcast | None:
        """Oldest **due** ``pending`` broadcast, FIFO by id (16.8 step 1; 9.5.10 due-poller).

        A row is due when ``scheduled_at`` is NULL (immediate) or ``scheduled_at <= now``.
        ``now`` defaults to the current time, so existing immediate broadcasts are
        unaffected.
        """
        cutoff = now if now is not None else _now()
        result = await self.session.execute(
            select(Broadcast)
            .where(
                Broadcast.status == "pending",
                or_(Broadcast.scheduled_at.is_(None), Broadcast.scheduled_at <= cutoff),
            )
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
