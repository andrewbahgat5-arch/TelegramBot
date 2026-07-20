"""ErrorLogRepository (MASTER_PLAN 10.12, partitioned)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select

from infrastructure.database.models import ErrorLog
from infrastructure.database.repositories.base import SqlAlchemyRepository


class ErrorLogRepository(SqlAlchemyRepository[ErrorLog]):
    model = ErrorLog

    async def record(
        self,
        *,
        error_type: str,
        message: str,
        user_id: int | None = None,
        job_id: uuid.UUID | None = None,
        correlation_id: uuid.UUID | None = None,
        traceback_text: str | None = None,
        severity: str | None = None,
        category: str | None = None,
        platform: str | None = None,
        url: str | None = None,
        url_host: str | None = None,
        username: str | None = None,
        chat_id: int | None = None,
        context_json: dict[str, object] | None = None,
    ) -> None:
        """Persist one error occurrence (Section 15.4 → ``error_logs``).

        ``error_type`` is capped to the column's 30 chars; the caller owns the
        transaction (repositories never commit)."""
        await self.add(
            ErrorLog(
                error_type=error_type[:30],
                message=message,
                user_id=user_id,
                job_id=job_id,
                correlation_id=correlation_id,
                traceback=traceback_text,
                severity=severity,
                category=category[:40] if category else None,
                platform=platform[:30] if platform else None,
                url=url,
                url_host=url_host[:255] if url_host else None,
                username=username[:64] if username else None,
                chat_id=chat_id,
                context=context_json,
            )
        )

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
