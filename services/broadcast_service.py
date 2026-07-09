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

import datetime
from collections.abc import Sequence
from typing import Any

from core.logging import get_logger
from domain.entities.audience import AudienceRuleSpec
from domain.enums import AudienceMode, UserRole
from domain.exceptions import AppError
from domain.protocols.repositories import (
    AudienceExpressionRepositoryProtocol,
    BroadcastRepositoryProtocol,
    UserRepositoryProtocol,
)

_log = get_logger("services.broadcast_service")

_VALID_ROLES = frozenset(role.value for role in UserRole)
_VALID_MODES = frozenset(mode.value for mode in AudienceMode)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


class InvalidBroadcastError(AppError):
    """The broadcast request is malformed (empty text or unknown role filter)."""


class BroadcastService:
    def __init__(
        self,
        *,
        broadcast_repo: BroadcastRepositoryProtocol[Any],
        user_repo: UserRepositoryProtocol[Any],
        expression_repo: AudienceExpressionRepositoryProtocol[Any] | None = None,
    ) -> None:
        self._broadcasts = broadcast_repo
        self._users = user_repo
        self._expressions = expression_repo

    async def _resolve_audience(
        self,
        *,
        audience_mode: str | None,
        audience_rules: Sequence[AudienceRuleSpec] | None,
        target_role: str | None,
        target_language: str | None,
    ) -> tuple[int, int | None]:
        """Snapshot the audience size and (when rule-based) persist its expression.

        Returns ``(expected_total, audience_expression_id)``. With ``audience_rules`` the
        unified engine is used (D-055): a new expression is created and counted via
        ``count_for_audience``; otherwise the legacy ``target_role`` / ``target_language``
        filter is counted. The two paths are mutually exclusive.
        """
        if audience_rules is not None:
            if self._expressions is None:  # pragma: no cover - composition wiring guarantee
                raise InvalidBroadcastError("Audience expressions are not available here.")
            mode = audience_mode or AudienceMode.ALL.value
            if mode not in _VALID_MODES:
                raise InvalidBroadcastError(f"Unknown audience mode: {mode}")
            rules = list(audience_rules)
            expression = await self._expressions.create(mode=mode)
            for rule in rules:
                await self._expressions.add_rule(
                    expression.id, effect=rule.effect, dimension=rule.dimension, value=rule.value
                )
            total = await self._users.count_for_audience(mode=mode, rules=rules, now=_now())
            return total, expression.id
        if target_role is not None and target_role not in _VALID_ROLES:
            raise InvalidBroadcastError(f"Unknown target role: {target_role}")
        total = await self._users.count_for_broadcast(role=target_role, language=target_language)
        return total, None

    async def estimate_recipients(
        self,
        *,
        audience_mode: str | None,
        audience_rules: Sequence[AudienceRuleSpec],
    ) -> int:
        """Count how many users a broadcast would reach, without persisting anything (#7).

        A read-only preview of the same audience the real ``create`` would snapshot — it
        runs the identical unified predicate (``count_for_audience``) but never creates an
        audience-expression row, so it is safe to call every time the Preview step renders.
        """
        mode = audience_mode or AudienceMode.ALL.value
        if mode not in _VALID_MODES:
            raise InvalidBroadcastError(f"Unknown audience mode: {mode}")
        return await self._users.count_for_audience(
            mode=mode, rules=list(audience_rules), now=_now()
        )

    async def create(
        self,
        *,
        created_by_user_id: int,
        message_text: str,
        target_language: str | None = None,
        target_role: str | None = None,
        scheduled_at: datetime.datetime | None = None,
        audience_mode: str | None = None,
        audience_rules: Sequence[AudienceRuleSpec] | None = None,
        status: str = "pending",
    ) -> Any:
        """Snapshot the audience size and queue a broadcast (16.8 step 1).

        ``scheduled_at`` (9.5.10) defers delivery until due; NULL = sent on the next poll.
        ``audience_rules`` (Sprint 9.6, D-055) targets a unified expression instead of the
        legacy ``target_role`` / ``target_language`` filter. ``status`` (Publish-vs-Save
        wizard flow) is ``pending`` (queued for the worker) or ``draft`` (saved, not sent —
        see :meth:`create_draft` / :meth:`publish_draft`).
        """
        text = message_text.strip()
        if not text:
            raise InvalidBroadcastError("Broadcast message text must not be empty.")
        expected_total, audience_expression_id = await self._resolve_audience(
            audience_mode=audience_mode,
            audience_rules=audience_rules,
            target_role=target_role,
            target_language=target_language,
        )
        broadcast = await self._broadcasts.create_pending(
            created_by=created_by_user_id,
            message_text=text,
            target_language=target_language,
            target_role=target_role,
            expected_total=expected_total,
            scheduled_at=scheduled_at,
            audience_expression_id=audience_expression_id,
            status=status,
        )
        _log.info(
            "broadcast_queued" if status == "pending" else "broadcast_saved",
            broadcast_id=broadcast.id,
            expected_total=expected_total,
            target_role=target_role,
            target_language=target_language,
            audience_expression_id=audience_expression_id,
            scheduled_at=scheduled_at.isoformat() if scheduled_at else None,
            status=status,
        )
        return broadcast

    async def create_draft(
        self,
        *,
        created_by_user_id: int,
        message_text: str,
        target_language: str | None = None,
        audience_mode: str | None = None,
        audience_rules: Sequence[AudienceRuleSpec] | None = None,
    ) -> Any:
        """Save a broadcast composition without queuing it for delivery (Save-for-later).

        A thin ``status="draft"`` wrapper over :meth:`create` — same audience snapshot and
        validation, just never picked up by the ``BroadcastWorker`` until
        :meth:`publish_draft` moves it to ``pending``.
        """
        return await self.create(
            created_by_user_id=created_by_user_id,
            message_text=message_text,
            target_language=target_language,
            audience_mode=audience_mode,
            audience_rules=audience_rules,
            status="draft",
        )

    async def publish_draft(self, broadcast_id: int) -> Any:
        """Move a saved draft to ``pending`` so the worker picks it up on its next poll."""
        broadcast = await self._broadcasts.get_by_id(broadcast_id)
        if broadcast is None:
            raise InvalidBroadcastError("Broadcast not found.")
        if broadcast.status != "draft":
            raise InvalidBroadcastError("Only draft broadcasts can be published.")
        await self._broadcasts.set_status(broadcast_id, "pending")
        return await self._broadcasts.get_by_id(broadcast_id)

    async def get_broadcast(self, broadcast_id: int) -> Any | None:
        return await self._broadcasts.get_by_id(broadcast_id)

    async def list_saved(self) -> list[Any]:
        """Every saved broadcast (draft + pending + completed), newest first."""
        return list(await self._broadcasts.list_all())

    async def create_from_ad(
        self,
        *,
        created_by_user_id: int,
        advertisement_id: int,
        target_language: str | None = None,
        target_role: str | None = None,
        scheduled_at: datetime.datetime | None = None,
        audience_mode: str | None = None,
        audience_rules: Sequence[AudienceRuleSpec] | None = None,
        status: str = "pending",
    ) -> Any:
        """Queue a broadcast that delivers a stored ad via copyMessage (Sprint 9.5, D-045).

        Reuses the Sprint 8 audience snapshot + chunked fan-out; the ``BroadcastWorker``
        copies the linked ad to each recipient instead of sending ``message_text``.
        ``scheduled_at`` (9.5.10) defers delivery until due; NULL = sent on the next poll.
        ``audience_rules`` (Sprint 9.6, D-055) targets a unified expression. ``status``
        (Publish-vs-Save wizard flow) is ``pending`` or ``draft`` (see :meth:`create`).
        """
        expected_total, audience_expression_id = await self._resolve_audience(
            audience_mode=audience_mode,
            audience_rules=audience_rules,
            target_role=target_role,
            target_language=target_language,
        )
        broadcast = await self._broadcasts.create_pending(
            created_by=created_by_user_id,
            message_text="",  # content comes from the linked ad
            target_language=target_language,
            target_role=target_role,
            expected_total=expected_total,
            advertisement_id=advertisement_id,
            scheduled_at=scheduled_at,
            audience_expression_id=audience_expression_id,
            status=status,
        )
        _log.info(
            "ad_broadcast_queued",
            broadcast_id=broadcast.id,
            advertisement_id=advertisement_id,
            expected_total=expected_total,
            audience_expression_id=audience_expression_id,
            scheduled_at=scheduled_at.isoformat() if scheduled_at else None,
        )
        return broadcast
