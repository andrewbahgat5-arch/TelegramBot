"""ErrorLogService — persist failures into ``error_logs`` (MASTER_PLAN 10.12).

The ``error_logs`` table existed since Sprint 8 but nothing wrote to it: failed
*analyses* never create a job row, so once the docker logs rotated they were gone.
This service is the write path — the bot's URL-analysis failure branches (and any
future caller) record one row per failure, giving the admin ``/v1/admin/errors``
browse and "what's breaking?" queries real data.

Recording is best-effort by design: a failure to log a failure must never mask or
break the user-facing flow, so every exception is swallowed (and logged).
"""

from __future__ import annotations

import traceback as tb
import uuid
from typing import Any

from core.logging import get_logger
from domain.exceptions import AppError
from domain.protocols.repositories import ErrorLogRepositoryProtocol

_log = get_logger("services.error_log_service")

# error_logs.message is Text, but a failure message is a diagnostic headline, not a
# dump — the full traceback goes in its own column.
_MESSAGE_CAP = 500


class ErrorLogService:
    def __init__(self, repo: ErrorLogRepositoryProtocol[Any]) -> None:
        self._repo = repo

    async def record_failure(
        self,
        error: BaseException,
        *,
        context: str,
        user_id: int | None = None,
        correlation_id: str | None = None,
        with_traceback: bool = False,
    ) -> None:
        """Persist one failure row. ``context`` is a short "where/what" prefix (e.g.
        ``"analyze youtube youtu.be c615f378dd02"``) so rows are greppable without
        joining logs. ``error_type`` comes from the domain hierarchy when the error
        is an :class:`AppError`, else the exception class name."""
        error_type = (
            error.error_type.value if isinstance(error, AppError) else type(error).__name__
        )
        trace = (
            "".join(tb.format_exception(type(error), error, error.__traceback__))
            if with_traceback
            else None
        )
        try:
            await self._repo.record(
                error_type=error_type,
                message=f"{context}: {error}"[:_MESSAGE_CAP],
                user_id=user_id,
                correlation_id=_parse_uuid(correlation_id),
                traceback_text=trace,
            )
        except Exception as exc:  # best-effort: never let logging break the flow
            _log.warning("error_log_write_failed", error=str(exc))


def _parse_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None
