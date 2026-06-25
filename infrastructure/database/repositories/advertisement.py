"""AdRepository (MASTER_PLAN 10.10, flow 16.7)."""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from typing import Any

from sqlalchemy import or_, select, update

from infrastructure.database.models import Advertisement
from infrastructure.database.repositories.base import SqlAlchemyRepository


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


class AdRepository(SqlAlchemyRepository[Advertisement]):
    model = Advertisement

    async def list_active_for_role(self, effective_role: str) -> Sequence[Advertisement]:
        """Active, role-matching ads ranked for selection (16.7 step 3).

        Untargeted ads (``target_role IS NULL``) always match; targeted ads match only
        the user's effective role. Ordering is ``priority`` DESC then ``id`` ASC so the
        caller can walk candidates highest-priority-first (index
        ``ix_ads_active_priority_role``).
        """
        result = await self.session.execute(
            select(Advertisement)
            .where(
                Advertisement.is_active.is_(True),
                or_(
                    Advertisement.target_role.is_(None),
                    Advertisement.target_role == effective_role,
                ),
            )
            .order_by(Advertisement.priority.desc(), Advertisement.id.asc())
        )
        return result.scalars().all()

    async def list_all_ads(self) -> Sequence[Advertisement]:
        """Every ad, ranked the same way, for the admin surface."""
        result = await self.session.execute(
            select(Advertisement).order_by(Advertisement.priority.desc(), Advertisement.id.asc())
        )
        return result.scalars().all()

    async def list_active_for_placement(self, placement: str) -> Sequence[Advertisement]:
        """Active ads for a placement, ranked priority DESC then id ASC (Sprint 9.5).

        Audience filtering is applied per-candidate by ``AudienceService`` (the rule
        set cannot be expressed as one indexed predicate). Uses
        ``ix_ads_placement_active_priority``.
        """
        result = await self.session.execute(
            select(Advertisement)
            .where(Advertisement.is_active.is_(True), Advertisement.placement == placement)
            .order_by(Advertisement.priority.desc(), Advertisement.id.asc())
        )
        return result.scalars().all()

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
    ) -> Advertisement:
        ad = Advertisement(
            title=title,
            type=ad_type,
            content_text=content_text,
            content_media_file_id=content_media_file_id,
            button_text=button_text,
            button_url=button_url,
            target_role=target_role,
            show_every_n_downloads=show_every_n_downloads,
            priority=priority,
            created_by=created_by,
            placement=placement,
            delivery_mode=delivery_mode,
            storage_chat_id=storage_chat_id,
            storage_message_id=storage_message_id,
            parse_mode=parse_mode,
            audience_mode=audience_mode,
        )
        return await self.add(ad)

    async def apply_update(self, ad: Advertisement, changes: dict[str, Any]) -> Advertisement:
        """Persist field edits on a loaded ad and bump ``updated_at`` (10.10)."""
        for key, value in changes.items():
            setattr(ad, key, value)
        ad.updated_at = _now()
        await self.session.flush()
        return ad

    async def increment_impressions(self, ad_id: int) -> None:
        await self.session.execute(
            update(Advertisement)
            .where(Advertisement.id == ad_id)
            .values(impressions=Advertisement.impressions + 1)
        )
        await self.session.flush()

    async def increment_clicks(self, ad_id: int) -> None:
        await self.session.execute(
            update(Advertisement)
            .where(Advertisement.id == ad_id)
            .values(clicks=Advertisement.clicks + 1)
        )
        await self.session.flush()
