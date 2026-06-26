"""ErrorLogRepository (MASTER_PLAN 10.12, partitioned)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select

from infrastructure.database.models import ErrorLog
from infrastructure.database.repositories.base import SqlAlchemyRepository


class ErrorLogRepository(SqlAlchemyRepository[ErrorLog]):
    model = ErrorLog

    async def list_recent(
        self, *, limit: int = 50, offset: int = 0, error_type: str | None = None
    ) -> Sequence[ErrorLog]:
        """Most-recent error rows first for the admin ``/v1/admin/errors`` browse (Task 8.3).

        Optionally filtered by ``error_type`` (Section 15.4 hierarchy). Ordered by
        ``created_at`` DESC (the partition key), with ``id`` as a stable tiebreak.
        """
        stmt = select(ErrorLog)
        if error_type is not None:
            stmt = stmt.where(ErrorLog.error_type == error_type)
        stmt = stmt.order_by(ErrorLog.created_at.desc(), ErrorLog.id).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return result.scalars().all()
