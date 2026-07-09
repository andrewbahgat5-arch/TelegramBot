"""AdRepository (MASTER_PLAN 10.10, flow 16.7)."""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from typing import Any

from sqlalchemy import and_, delete, exists, or_, select, update

from infrastructure.database.models import Advertisement
from infrastructure.database.models.ad_placement import AdPlacementLink
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
        """Active ads for a placement, ranked for fair selection (Sprint 9.5; UX sprint #10).

        Ordering **is** the scheduling strategy (priority tier + least-recently-shown):
        ``priority`` DESC, then ``last_shown_at`` ASC with NULLs first, then ``id`` ASC. The
        caller walks candidates in this order and delivers the first that is due + audience-
        matching, so among equal-priority ads that are all due, the one shown longest ago
        (or never) wins — a deterministic, self-correcting round-robin. Swapping this ORDER
        BY is how a future strategy (weighted, A/B, …) would plug in.

        Multi-placement dual-read (Sprint 9.6, D-056): an ad matches when it has an
        ``ad_placements`` row for ``placement``, *or* — for legacy ads with no placement
        rows — when its scalar ``placement`` column matches. Audience filtering is applied
        per-candidate by ``AudienceService`` (the rule set is not one indexed predicate).
        """
        has_link = exists().where(
            AdPlacementLink.advertisement_id == Advertisement.id,
            AdPlacementLink.placement == placement,
        )
        has_any_link = exists().where(AdPlacementLink.advertisement_id == Advertisement.id)
        result = await self.session.execute(
            select(Advertisement)
            .where(
                Advertisement.is_active.is_(True),
                or_(has_link, and_(~has_any_link, Advertisement.placement == placement)),
            )
            .order_by(
                Advertisement.priority.desc(),
                Advertisement.last_shown_at.asc().nulls_first(),
                Advertisement.id.asc(),
            )
        )
        return result.scalars().all()

    async def list_placements(self, ad_id: int) -> list[str]:
        """The placements an ad occupies (Sprint 9.6, D-056)."""
        result = await self.session.execute(
            select(AdPlacementLink.placement)
            .where(AdPlacementLink.advertisement_id == ad_id)
            .order_by(AdPlacementLink.placement.asc())
        )
        return list(result.scalars().all())

    async def set_placements(self, ad_id: int, placements: Sequence[str]) -> None:
        """Replace an ad's placement set (Sprint 9.6, D-056)."""
        await self.session.execute(
            delete(AdPlacementLink).where(AdPlacementLink.advertisement_id == ad_id)
        )
        for placement in dict.fromkeys(placements):  # de-dupe, preserve order
            self.session.add(AdPlacementLink(advertisement_id=ad_id, placement=placement))
        await self.session.flush()

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
        target_language: str | None = None,
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
            scheduled_at=scheduled_at,
            internal_name=internal_name,
            internal_notes=internal_notes,
            target_language=target_language,
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
        # Stamp last_shown_at in the same write so the fair-rotation cursor (#10) advances
        # exactly when an impression is recorded — no extra round-trip on the delivery path.
        await self.session.execute(
            update(Advertisement)
            .where(Advertisement.id == ad_id)
            .values(impressions=Advertisement.impressions + 1, last_shown_at=_now())
        )
        await self.session.flush()

    async def increment_clicks(self, ad_id: int) -> None:
        await self.session.execute(
            update(Advertisement)
            .where(Advertisement.id == ad_id)
            .values(clicks=Advertisement.clicks + 1)
        )
        await self.session.flush()
