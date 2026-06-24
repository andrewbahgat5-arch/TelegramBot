"""BroadcastService (MASTER_PLAN Component 9.2, Task 8.1, flow 16.8).

Queues an admin broadcast for delivery. ``create`` snapshots the matching audience
size into ``broadcasts.expected_total`` and inserts a ``pending`` row; the
``BroadcastWorker`` (which polls the durable ``broadcasts`` table) does the actual
fan-out. Filtering is by optional ``target_role`` / ``target_language`` (NULL = all);
banned users are always excluded from the audience.

Design note (deviation from §16.8 wording, surfaced for Owner): the worker reads
``pending`` rows from the ``broadcasts`` table rather than the shared ``queue:jobs``
sorted set. V1's ``RedisQueue`` does not dispatch by ``worker_kind`` (the download
worker ``BZPOPMIN``-pops any member and treats it as a job UUID), so putting a
broadcast on that queue would corrupt the download path. Polling the durable table
matches the ``BroadcastWorker`` component card (no ``QueueService`` dependency) and
the locked §11.4 key set (which has no broadcast queue key).
"""

from __future__ import annotations

from typing import Any

from core.logging import get_logger
from domain.enums import UserRole
from domain.exceptions import AppError
from domain.protocols.repositories import (
    BroadcastRepositoryProtocol,
    UserRepositoryProtocol,
)

_log = get_logger("services.broadcast_service")

_VALID_ROLES = frozenset(role.value for role in UserRole)


class InvalidBroadcastError(AppError):
    """The broadcast request is malformed (empty text or unknown role filter)."""


class BroadcastService:
    def __init__(
        self,
        *,
        broadcast_repo: BroadcastRepositoryProtocol[Any],
        user_repo: UserRepositoryProtocol[Any],
    ) -> None:
        self._broadcasts = broadcast_repo
        self._users = user_repo

    async def create(
        self,
        *,
        created_by_user_id: int,
        message_text: str,
        target_language: str | None = None,
        target_role: str | None = None,
    ) -> Any:
        """Snapshot the audience size and queue a ``pending`` broadcast (16.8 step 1)."""
        text = message_text.strip()
        if not text:
            raise InvalidBroadcastError("Broadcast message text must not be empty.")
        if target_role is not None and target_role not in _VALID_ROLES:
            raise InvalidBroadcastError(f"Unknown target role: {target_role}")

        expected_total = await self._users.count_for_broadcast(
            role=target_role, language=target_language
        )
        broadcast = await self._broadcasts.create_pending(
            created_by=created_by_user_id,
            message_text=text,
            target_language=target_language,
            target_role=target_role,
            expected_total=expected_total,
        )
        _log.info(
            "broadcast_queued",
            broadcast_id=broadcast.id,
            expected_total=expected_total,
            target_role=target_role,
            target_language=target_language,
        )
        return broadcast
