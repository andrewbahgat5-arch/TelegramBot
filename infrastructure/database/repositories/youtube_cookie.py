"""YoutubeCookieRepository — metadata, health and statistics (DESIGN_COOKIE_POOL.md §6).

Statistics are written straight to Postgres rather than buffered through Redis: two
UPDATEs per download at the current scale is well under one write per second, and the
extra moving part would buy nothing. If selection volume ever makes that matter, the
counter columns are the only thing that needs a buffered writer.
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import select, update

from domain.entities.cookie import CookieImpact, CookieSnapshot, CookieVerdict
from domain.enums.cookie_health import SELECTABLE_HEALTH, CookieHealth
from infrastructure.database.models import YoutubeCookie, YoutubeCookieEvent
from infrastructure.database.repositories.base import SqlAlchemyRepository


def _to_snapshot(row: YoutubeCookie) -> CookieSnapshot:
    return CookieSnapshot(
        id=row.id,
        label=row.label,
        status=CookieHealth(row.status),
        file_version=row.file_version,
        egress_id=row.egress_id,
        cooldown_until=row.cooldown_until,
        auth_failures=row.auth_failures,
        cooldown_cycles=row.cooldown_cycles,
        total_uses=row.total_uses,
        total_success=row.total_success,
        total_auth_failures=row.total_auth_failures,
        total_other_failures=row.total_other_failures,
        last_used_at=row.last_used_at,
        last_success_at=row.last_success_at,
        last_failure_at=row.last_failure_at,
        last_failure_reason=row.last_failure_reason,
    )


class YoutubeCookieRepository(SqlAlchemyRepository[YoutubeCookie]):
    model = YoutubeCookie

    async def list_all(self) -> list[CookieSnapshot]:
        result = await self.session.execute(select(YoutubeCookie).order_by(YoutubeCookie.label))
        return [_to_snapshot(r) for r in result.scalars().all()]

    async def get(self, cookie_id: int) -> CookieSnapshot | None:
        row = await self.session.get(YoutubeCookie, cookie_id)
        return _to_snapshot(row) if row else None

    async def get_by_label(self, label: str) -> CookieSnapshot | None:
        result = await self.session.execute(
            select(YoutubeCookie).where(YoutubeCookie.label == label).limit(1)
        )
        row = result.scalar_one_or_none()
        return _to_snapshot(row) if row else None

    async def list_candidates(
        self, *, egress_id: str, now: datetime.datetime
    ) -> list[CookieSnapshot]:
        """Every selectable cookie. Affinity ordering is applied by the service, which
        keeps that policy pure and unit-testable; the DB only filters."""
        stmt = (
            select(YoutubeCookie)
            .where(YoutubeCookie.status.in_([s.value for s in SELECTABLE_HEALTH]))
            .where(
                (YoutubeCookie.cooldown_until.is_(None)) | (YoutubeCookie.cooldown_until <= now)
            )
        )
        result = await self.session.execute(stmt)
        return [_to_snapshot(r) for r in result.scalars().all()]

    async def create(
        self,
        *,
        label: str,
        file_version: int,
        content_hash: str,
        created_by: int | None = None,
        egress_id: str | None = None,
    ) -> CookieSnapshot:
        row = YoutubeCookie(
            label=label,
            status=CookieHealth.HEALTHY.value,
            file_version=file_version,
            content_hash=content_hash,
            created_by=created_by,
            egress_id=egress_id,
        )
        await self.add(row)
        return _to_snapshot(row)

    async def record_use(self, cookie_id: int, *, at: datetime.datetime) -> None:
        await self.session.execute(
            update(YoutubeCookie)
            .where(YoutubeCookie.id == cookie_id)
            .values(last_used_at=at, total_uses=YoutubeCookie.total_uses + 1)
        )

    async def record_outcome(
        self,
        cookie_id: int,
        *,
        verdict: CookieVerdict,
        status: CookieHealth,
        cooldown_until: datetime.datetime | None,
        auth_failures: int,
        cooldown_cycles: int,
        at: datetime.datetime,
    ) -> None:
        values: dict[str, Any] = {
            "status": status.value,
            "cooldown_until": cooldown_until,
            "auth_failures": auth_failures,
            "cooldown_cycles": cooldown_cycles,
            "updated_at": at,
        }
        if verdict.impact is CookieImpact.SUCCESS:
            values["total_success"] = YoutubeCookie.total_success + 1
            values["last_success_at"] = at
        elif verdict.affects_health:
            values["total_auth_failures"] = YoutubeCookie.total_auth_failures + 1
            values["last_failure_at"] = at
            values["last_failure_reason"] = verdict.reason[:500]
        else:
            # Route / content / unclassified: counted for the statistics page, and
            # deliberately kept out of every health-bearing column.
            values["total_other_failures"] = YoutubeCookie.total_other_failures + 1
            values["last_failure_at"] = at
            values["last_failure_reason"] = verdict.reason[:500]
        await self.session.execute(
            update(YoutubeCookie).where(YoutubeCookie.id == cookie_id).values(**values)
        )

    async def set_status(
        self,
        cookie_id: int,
        *,
        status: CookieHealth,
        actor_user_id: int | None = None,
        reason: str = "",
    ) -> None:
        current = await self.get(cookie_id)
        await self.session.execute(
            update(YoutubeCookie)
            .where(YoutubeCookie.id == cookie_id)
            .values(status=status.value, cooldown_until=None)
        )
        await self.add_event(
            cookie_id,
            event="cookie_health_changed",
            from_status=current.status if current else None,
            to_status=status,
            reason=reason,
            actor_user_id=actor_user_id,
        )

    async def set_egress(self, cookie_id: int, egress_id: str) -> None:
        await self.session.execute(
            update(YoutubeCookie).where(YoutubeCookie.id == cookie_id).values(egress_id=egress_id)
        )

    async def replace_file(
        self,
        cookie_id: int,
        *,
        expected_version: int,
        new_version: int,
        content_hash: str,
        actor_user_id: int | None = None,
    ) -> bool:
        """Compare-and-swap on ``file_version``.

        Returns False when another admin replaced the same cookie while this upload was
        in flight — the caller must not overwrite their newer file.
        """
        result = await self.session.execute(
            update(YoutubeCookie)
            .where(YoutubeCookie.id == cookie_id)
            .where(YoutubeCookie.file_version == expected_version)
            .values(
                file_version=new_version,
                content_hash=content_hash,
                status=CookieHealth.HEALTHY.value,
                cooldown_until=None,
                auth_failures=0,
                cooldown_cycles=0,
                last_failure_reason=None,
            )
        )
        replaced = bool(result.rowcount)
        if replaced:
            await self.add_event(
                cookie_id,
                event="cookie_replaced",
                to_status=CookieHealth.HEALTHY,
                reason=f"replaced with v{new_version}",
                actor_user_id=actor_user_id,
            )
        return replaced

    async def add_event(
        self,
        cookie_id: int,
        *,
        event: str,
        from_status: CookieHealth | None = None,
        to_status: CookieHealth | None = None,
        reason: str = "",
        egress_id: str | None = None,
        actor_user_id: int | None = None,
    ) -> None:
        self.session.add(
            YoutubeCookieEvent(
                cookie_id=cookie_id,
                event=event,
                from_status=from_status.value if from_status else None,
                to_status=to_status.value if to_status else None,
                reason=reason[:1000] or None,
                egress_id=egress_id,
                actor_user_id=actor_user_id,
            )
        )

    async def list_events(self, cookie_id: int, *, limit: int = 20) -> list[YoutubeCookieEvent]:
        result = await self.session.execute(
            select(YoutubeCookieEvent)
            .where(YoutubeCookieEvent.cookie_id == cookie_id)
            .order_by(YoutubeCookieEvent.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
