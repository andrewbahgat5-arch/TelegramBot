"""Repository protocols (MASTER_PLAN Task 2.6, Component 9.4).

These interfaces are what the service layer depends on. They are deliberately
model-agnostic — ``domain`` may not import ``infrastructure`` (Section 8) — so each
protocol is generic over the entity type ``T`` that the concrete repository binds.
Concrete repositories in ``infrastructure/database/repositories`` satisfy these
structurally.

Repositories never commit; they ``add``/``flush`` only. The unit of work is owned
by the entry point (e.g. ``DbSessionMiddleware``).
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Sequence
from typing import Any, Protocol, TypeVar

from domain.entities.audience import AudienceRuleSpec
from domain.entities.reward import Reward
from domain.rewards import RewardType

T = TypeVar("T")


class Repository(Protocol[T]):
    """Common CRUD surface shared by all repositories."""

    async def add(self, entity: T) -> T: ...
    async def get_by_id(self, id_: Any) -> T | None: ...
    async def list_paginated(self, *, limit: int = 50, offset: int = 0) -> Sequence[T]: ...
    async def delete(self, entity: T) -> None: ...


class RewardRepositoryProtocol(Protocol):
    """Persistence for granted rewards (the Reward Engine, D-075).

    Returns domain :class:`~domain.entities.reward.Reward` snapshots (not ORM rows).
    ``list_active`` / ``list_all_active`` return only rewards active at ``now``
    (a null ``expires_at`` is permanent) — the caller aggregates per the type's
    stacking rule.
    """

    async def create(
        self,
        *,
        user_id: int,
        reward_type: RewardType,
        value: int,
        param: str | None,
        source: str,
        expires_at: datetime.datetime | None,
    ) -> Reward: ...
    async def list_active(
        self, user_id: int, reward_type: RewardType, *, now: datetime.datetime
    ) -> list[Reward]: ...
    async def list_all_active(self, user_id: int, *, now: datetime.datetime) -> list[Reward]: ...


class UserRepositoryProtocol(Repository[T], Protocol[T]):
    async def get_by_telegram_id(self, telegram_id: int) -> T | None: ...
    async def create_user(
        self,
        *,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        language: str | None,
        role: str,
    ) -> T: ...
    async def touch_last_activity(self, telegram_id: int, when: datetime.datetime) -> None: ...
    async def reset_daily_download_count_if_needed(
        self, user: T, *, today: datetime.date | None = None
    ) -> T: ...
    async def increment_download_counters(
        self, user_id: int, *, today: datetime.date | None = None
    ) -> None:
        """Atomic, lazy-reset counter bump for one completed download (16.6, D-012)."""
        ...

    async def count_all(self) -> int:
        """Total registered users (admin /stats)."""
        ...

    async def count_banned(self) -> int:
        """Currently-banned users (admin /stats)."""
        ...

    async def sum_total_downloads(self) -> int:
        """Lifetime delivered-download count across all users (admin /stats)."""
        ...

    async def count_created_since(self, since: datetime.datetime) -> int:
        """Users whose ``created_at`` is at or after ``since`` (joined-today / -week stats)."""
        ...

    async def count_active_since(self, since: datetime.datetime) -> int:
        """Users whose ``last_activity_at`` is at or after ``since`` (active-today stat)."""
        ...

    async def count_active_in_hours(self, hours: int) -> int:
        """Users active within the last ``hours`` (13.4 activity metrics)."""
        ...

    async def count_inactive_days(self, days: int) -> int:
        """Users last active before ``days`` ago, or never active (13.4)."""
        ...

    async def count_active_current_hour(self) -> int:
        """Users active within the current clock hour (13.4)."""
        ...

    async def count_active_previous_hour(self) -> int:
        """Users active within the previous clock hour only (13.4)."""
        ...

    async def count_premium(self) -> int:
        """Users currently flagged premium (admin stats)."""
        ...

    async def count_staff(self) -> int:
        """Users with an Owner or Moderator role (admin stats)."""
        ...

    # User-health detection (Sprint 13.5).
    async def count_blocked(self) -> int:
        """Users flagged as having blocked the bot."""
        ...

    async def count_deleted(self) -> int:
        """Users whose Telegram account is flagged deleted/deactivated."""
        ...

    async def list_blocked(self, *, limit: int = 30, offset: int = 0) -> Sequence[T]:
        """A page of blocked users (id ascending)."""
        ...

    async def list_deleted(self, *, limit: int = 30, offset: int = 0) -> Sequence[T]:
        """A page of deleted-account users (id ascending)."""
        ...

    async def mark_blocked(self, telegram_id: int) -> None:
        """Flag a user as having blocked the bot; records the probe time."""
        ...

    async def mark_deleted(self, telegram_id: int) -> None:
        """Flag a user's account as deleted/deactivated; records the probe time."""
        ...

    async def mark_active(self, telegram_id: int) -> None:
        """Clear both health flags after a successful probe; records the probe time."""
        ...

    async def get_unchecked_ids(self, *, limit: int = 100) -> list[int]:
        """Telegram ids to probe next: never-checked first, then oldest checked."""
        ...

    async def purge_blocked(self) -> int:
        """Delete every ``bot_blocked`` user; returns the number removed."""
        ...

    async def purge_deleted(self) -> int:
        """Delete every ``is_deleted`` user; returns the number removed."""
        ...

    # Referral system (Sprint 13.7).
    async def get_by_referral_code(self, code: str) -> T | None:
        """Find the user owning a referral code, or None."""
        ...

    async def set_referral_code(self, user_id: int, code: str) -> None:
        """Persist a user's generated referral code."""
        ...

    async def set_referred_by(self, user_id: int, referrer_id: int) -> None:
        """Record which user (``users.id``) referred this user."""
        ...

    async def add_referral_bonus(self, user_id: int, amount: int) -> None:
        """Atomically add permanent bonus downloads to a user."""
        ...

    async def count_for_broadcast(self, *, role: str | None, language: str | None) -> int:
        """Count the non-banned audience matching the broadcast filters (16.8)."""
        ...

    async def page_for_broadcast(
        self, *, after_id: int, limit: int, role: str | None, language: str | None
    ) -> Sequence[T]:
        """One id-cursor page of the non-banned broadcast audience, ascending (16.8)."""
        ...

    async def count_for_audience(
        self, *, mode: str, rules: Sequence[AudienceRuleSpec], now: datetime.datetime
    ) -> int:
        """Count the broadcast audience defined by a unified expression (Sprint 9.6, D-055)."""
        ...

    async def page_for_audience(
        self,
        *,
        after_id: int,
        limit: int,
        mode: str,
        rules: Sequence[AudienceRuleSpec],
        now: datetime.datetime,
    ) -> Sequence[T]:
        """One id-cursor page of the unified-expression broadcast audience (Sprint 9.6)."""
        ...


class MediaRepositoryProtocol(Repository[T], Protocol[T]):
    async def get_by_platform_video(self, platform: str, video_id: str) -> T | None: ...
    async def upsert_metadata(
        self,
        *,
        platform: str,
        video_id: str,
        title: str,
        source_url: str,
        duration: int | None = None,
        thumbnail_url: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> T: ...


class CachedFileRepositoryProtocol(Repository[T], Protocol[T]):
    async def get_by_media_format_quality(
        self, media_id: int, format_: str, quality: str
    ) -> T | None: ...
    async def upsert(
        self,
        *,
        media_id: int,
        format_: str,
        quality: str,
        telegram_file_id: str,
        telegram_unique_file_id: str,
        file_size: int | None,
    ) -> T:
        """UPSERT on ``(media_id, format, quality)``; bump usage + last_used (16.1 W5)."""
        ...

    async def bump_usage(self, cached_file_id: int) -> None:
        """Increment usage_count and refresh last_used_at on a cache hit (16.2)."""
        ...


class JobRepositoryProtocol(Repository[T], Protocol[T]):
    async def get_by_uuid(self, job_id: uuid.UUID) -> T | None: ...
    async def count_active_for_user(
        self, user_id: int, *, within_seconds: int | None = None
    ) -> int:
        """Count this user's recent non-terminal jobs (free single-active cap, #16/#24)."""
        ...

    async def create(
        self,
        *,
        job_id: uuid.UUID,
        user_id: int,
        media_id: int,
        format_: str,
        quality: str,
        priority: int,
        correlation_id: uuid.UUID | None,
        status: str,
    ) -> T:
        """Insert a ``jobs`` row with an app-generated UUIDv7 id (D-013)."""
        ...

    async def set_status(
        self,
        job_id: uuid.UUID,
        status: str,
        *,
        started_at: datetime.datetime | None = None,
        finished_at: datetime.datetime | None = None,
        error_message: str | None = None,
        increment_retry: bool = False,
    ) -> None:
        """Advance a job's state machine (Section 12.3) by id (UPDATE only)."""
        ...


class ActiveDownloadRepositoryProtocol(Repository[T], Protocol[T]):
    async def get_by_media_format_quality(
        self, media_id: int, format_: str, quality: str
    ) -> T | None: ...
    async def insert_if_absent(
        self, *, media_id: int, format_: str, quality: str, job_id: uuid.UUID
    ) -> bool:
        """INSERT ON CONFLICT DO NOTHING; True if inserted, False on duplicate (16.1)."""
        ...

    async def delete_by_job(self, job_id: uuid.UUID) -> int:
        """Remove the active-download marker for a finished job (16.1 W9)."""
        ...


class JobWaiterRepositoryProtocol(Repository[T], Protocol[T]):
    async def list_for_job(self, job_id: uuid.UUID) -> Sequence[T]: ...
    async def delete_for_job(self, job_id: uuid.UUID) -> int: ...
    async def add_waiter(
        self, *, job_id: uuid.UUID, user_id: int, correlation_id: uuid.UUID | None
    ) -> bool:
        """INSERT ON CONFLICT (job_id,user_id) DO NOTHING; True if newly added (12.4)."""
        ...


class SettingsStoreProtocol(Protocol):
    """The settings persistence surface that ``SettingsService`` depends on.

    Returns are ``Any`` (a settings-row-like object exposing ``value: str`` and
    ``value_type: str``). ``Any`` avoids coupling the protocol to the ORM model,
    whose ``Mapped[str]`` columns do not structurally match a ``str`` attribute.
    """

    async def get_by_key(self, key: str) -> Any: ...
    async def upsert(self, key: str, value: str, *, updated_by: int | None = None) -> Any: ...
    async def list_all(self) -> Sequence[Any]:
        """Every settings row (admin ``/settings`` listing). Rows expose ``key``/``value``."""
        ...


class SettingsRepositoryProtocol(Repository[T], Protocol[T]):
    async def get_by_key(self, key: str) -> T | None: ...
    async def upsert(self, key: str, value: str, *, updated_by: int | None = None) -> T: ...


class DownloadRepositoryProtocol(Repository[T], Protocol[T]):
    async def list_for_user(
        self, user_id: int, *, limit: int = 10, offset: int = 0
    ) -> Sequence[T]: ...
    async def get_for_user(self, download_id: int, user_id: int) -> T | None:
        """Fetch one history row by id, scoped to its owner (resend, 16.3)."""
        ...

    async def create_completed(
        self,
        *,
        user_id: int,
        cached_file_id: int | None,
        platform: str,
        format_: str,
        quality: str,
        file_size: int | None,
        status: str = "completed",
    ) -> T:
        """Insert a denormalized history row for a delivered download (10.5, 16.1 W7)."""
        ...


class BroadcastRepositoryProtocol(Repository[T], Protocol[T]):
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
    ) -> T:
        """Insert a ``broadcasts`` row in ``pending`` state for the worker (10.9, 16.8).

        ``scheduled_at`` (9.5.10) defers delivery until due; NULL = immediate.
        ``audience_expression_id`` (Sprint 9.6, D-055) targets a unified audience
        expression; NULL = legacy ``target_role`` / ``target_language``.
        """
        ...

    async def get_next_pending(self, *, now: datetime.datetime | None = None) -> T | None:
        """Oldest **due** ``pending`` broadcast for the worker (16.8; 9.5.10 due-poller).

        Due = ``scheduled_at`` NULL or ``<= now`` (``now`` defaults to current time).
        """
        ...

    async def set_status(
        self, broadcast_id: int, status: str, *, completed_at: datetime.datetime | None = None
    ) -> None:
        """Advance a broadcast's lifecycle (pending → in_progress → completed)."""
        ...

    async def add_counts(self, broadcast_id: int, *, sent: int, failed: int) -> None:
        """Increment ``total_sent`` / ``total_failed`` after a delivered chunk (16.8)."""
        ...


class AudienceExpressionRepositoryProtocol(Repository[T], Protocol[T]):
    """CRUD for the unified audience expression + its rules (Sprint 9.6, D-055)."""

    async def create(self, *, mode: str) -> T:
        """Create an audience expression with the given mode (all/include/exclude)."""
        ...

    async def add_rule(self, expression_id: int, *, effect: str, dimension: str, value: str) -> Any:
        """Append one rule to an expression."""
        ...

    async def get_rules(self, expression_id: int) -> tuple[str, list[AudienceRuleSpec]] | None:
        """Return ``(mode, rules)`` for an expression, or None when it does not exist."""
        ...


class AdRepositoryProtocol(Repository[T], Protocol[T]):
    async def list_active_for_role(self, effective_role: str) -> Sequence[T]:
        """Active ads matching ``effective_role`` or untargeted, ranked for selection.

        WHERE ``is_active`` AND (``target_role`` IS NULL OR ``target_role`` =
        ``effective_role``), ORDER BY ``priority`` DESC, ``id`` ASC (flow 16.7 step 3,
        index ``ix_ads_active_priority_role``).
        """
        ...

    async def list_all_ads(self) -> Sequence[T]:
        """Every ad for the admin ``/ad_list`` / ``/ad_stats`` surface, ranked."""
        ...

    async def create_ad(
        self,
        *,
        title: str,
        ad_type: str,
        content_text: str | None,
        content_media_file_id: str | None,
        button_text: str | None,
        button_url: str | None,
        target_role: str | None,
        show_every_n_downloads: int,
        priority: int,
        created_by: int,
        placement: str = "post_download",
        delivery_mode: str = "fields",
        storage_chat_id: int | None = None,
        storage_message_id: int | None = None,
        parse_mode: str | None = None,
        audience_mode: str = "all",
        scheduled_at: datetime.datetime | None = None,
        internal_name: str | None = None,
        internal_notes: str | None = None,
    ) -> T:
        """Insert an ``advertisements`` row (10.10 + Sprint 9.5). ORM stays in infra.

        ``scheduled_at`` (9.5.10) gates placement selection until its start time; NULL =
        eligible immediately.
        """
        ...

    async def apply_update(self, ad: T, changes: dict[str, Any]) -> T:
        """Set ``changes`` on a loaded ad row, refresh ``updated_at``, flush (10.10)."""
        ...

    async def increment_impressions(self, ad_id: int) -> None:
        """Atomic ``impressions += 1`` after a delivered ad (flow 16.7 step 5)."""
        ...

    async def increment_clicks(self, ad_id: int) -> None:
        """Atomic ``clicks += 1`` when a user taps the ad's button (flow 16.7 step 6)."""
        ...

    async def list_active_for_placement(self, placement: str) -> Sequence[T]:
        """Active ads for a placement, ranked priority DESC, id ASC (Sprint 9.5, D-044).

        Multi-placement dual-read (Sprint 9.6, D-056): matches an ``ad_placements`` row or,
        for legacy ads with none, the scalar ``placement`` column.
        """
        ...

    async def list_placements(self, ad_id: int) -> list[str]:
        """The placements an ad occupies (Sprint 9.6, D-056)."""
        ...

    async def set_placements(self, ad_id: int, placements: Sequence[str]) -> None:
        """Replace an ad's placement set (Sprint 9.6, D-056)."""
        ...


class AdButtonRepositoryProtocol(Repository[T], Protocol[T]):
    async def list_for_ad(self, ad_id: int) -> Sequence[T]:
        """An ad's buttons in keyboard order (row, position) (Sprint 9.5)."""
        ...

    async def create_button(
        self, *, advertisement_id: int, text: str, url: str | None, row: int, position: int
    ) -> T: ...
    async def delete_for_ad(self, ad_id: int) -> int: ...
    async def increment_clicks(self, button_id: int) -> None: ...


class AdAudienceRuleRepositoryProtocol(Repository[T], Protocol[T]):
    async def list_for_ad(self, ad_id: int) -> Sequence[T]:
        """An ad's audience rules (Sprint 9.5, D-043)."""
        ...

    async def create_rule(
        self, *, advertisement_id: int, effect: str, dimension: str, value: str
    ) -> T: ...
    async def delete_for_ad(self, ad_id: int) -> int: ...


class AudienceSegmentRepositoryProtocol(Repository[T], Protocol[T]):
    async def create_segment(self, *, name: str, description: str | None, created_by: int) -> T: ...
    async def get_by_name(self, name: str) -> T | None: ...
    async def list_all_segments(self) -> Sequence[T]: ...


class AudienceSegmentMemberRepositoryProtocol(Protocol):
    async def add_member(self, *, segment_id: int, user_id: int) -> bool:
        """INSERT ON CONFLICT DO NOTHING; True if newly added (Sprint 9.5)."""
        ...

    async def remove_member(self, *, segment_id: int, user_id: int) -> bool: ...
    async def list_segment_ids_for_user(self, user_id: int) -> set[int]: ...
    async def count_members(self, segment_id: int) -> int: ...


class ReferralRepositoryProtocol(Repository[T], Protocol[T]):
    """CRUD + analytics for the ``referrals`` table (Sprint 13.7)."""

    async def create(
        self, *, referrer_id: int, referred_id: int, reward_granted: bool = True
    ) -> T: ...
    async def exists_for_referred(self, referred_id: int) -> bool: ...
    async def count_all(self) -> int: ...
    async def count_since(self, since: datetime.datetime) -> int: ...
    async def count_rewarded(self) -> int: ...
    async def count_for_referrer(self, referrer_id: int) -> int: ...
    async def leaderboard(self, *, limit: int = 10) -> list[tuple[int, str | None, str, int, int]]:
        """Top referrers: ``(telegram_id, username, first_name, invites, bonus)``."""
        ...


class ErrorLogRepositoryProtocol(Repository[T], Protocol[T]): ...


class UserPreferenceRepositoryProtocol(Repository[T], Protocol[T]):
    async def get_by_user_id(self, user_id: int) -> T | None: ...
