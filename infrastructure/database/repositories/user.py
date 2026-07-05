"""UserRepository (MASTER_PLAN 10.2, D-012)."""

from __future__ import annotations

import datetime
from collections.abc import Sequence

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.sql.elements import ColumnElement

from domain.entities.audience import AudienceRuleSpec
from domain.enums import UserRole
from infrastructure.database.audience_query import broadcast_audience_predicate
from infrastructure.database.models import User
from infrastructure.database.repositories.base import SqlAlchemyRepository

# Admin roles excluded from an untargeted broadcast (item #14): a default broadcast
# reaches normal users only, never the Owner/Moderator accounts.
_STAFF_ROLES = (UserRole.OWNER.value, UserRole.MODERATOR.value)


class UserRepository(SqlAlchemyRepository[User]):
    model = User

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    async def create_user(
        self,
        *,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        language: str | None,
        role: str,
    ) -> User:
        """Insert a new ``users`` row. ORM construction stays in infrastructure."""
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            language=language,
            role=role,
        )
        return await self.add(user)

    async def touch_last_activity(self, telegram_id: int, when: datetime.datetime) -> None:
        """Set ``last_activity_at`` without loading the row (debounced hot path).

        A targeted UPDATE keeps the user-cache fast path (D-014) cheap: on a cache
        hit we never load the ORM row, so the activity write must not require it.
        """
        await self.session.execute(
            update(User)
            .where(User.telegram_id == telegram_id)
            .values(last_activity_at=when, updated_at=when)
        )

    async def reset_daily_download_count_if_needed(
        self, user: User, *, today: datetime.date | None = None
    ) -> User:
        """Lazily reset the daily counter when the stored reset date is stale (D-012)."""
        current = today or datetime.datetime.now(datetime.UTC).date()
        if user.daily_download_count_reset_date < current:
            user.daily_download_count = 0
            user.daily_download_count_reset_date = current
            await self.session.flush()
        return user

    async def increment_download_counters(
        self, user_id: int, *, today: datetime.date | None = None
    ) -> None:
        """Bump ``total_downloads`` and the lazily-reset ``daily_download_count`` (16.6).

        A single atomic UPDATE keyed by id; the CASE resets the daily counter when
        its stored reset date is not today (D-012), avoiding a midnight batch.
        """
        current = today or datetime.datetime.now(datetime.UTC).date()
        daily = case(
            (
                User.daily_download_count_reset_date == current,
                User.daily_download_count + 1,
            ),
            else_=1,
        )
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                total_downloads=User.total_downloads + 1,
                daily_download_count=daily,
                daily_download_count_reset_date=current,
            )
        )
        await self.session.flush()

    async def count_all(self) -> int:
        result = await self.session.execute(select(func.count()).select_from(User))
        return int(result.scalar_one())

    async def count_banned(self) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(User).where(User.is_banned.is_(True))
        )
        return int(result.scalar_one())

    async def sum_total_downloads(self) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.sum(User.total_downloads), 0))
        )
        return int(result.scalar_one())

    async def count_created_since(self, since: datetime.datetime) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(User).where(User.created_at >= since)
        )
        return int(result.scalar_one())

    async def count_active_since(self, since: datetime.datetime) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(User).where(User.last_activity_at >= since)
        )
        return int(result.scalar_one())

    async def count_active_in_hours(self, hours: int) -> int:
        """Users with ``last_activity_at`` within the last ``hours`` (13.4 activity)."""
        since = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=hours)
        result = await self.session.execute(
            select(func.count()).select_from(User).where(User.last_activity_at >= since)
        )
        return int(result.scalar_one())

    async def count_inactive_days(self, days: int) -> int:
        """Users last active before ``days`` ago, OR never active (NULL) (13.4)."""
        cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days)
        result = await self.session.execute(
            select(func.count())
            .select_from(User)
            .where(or_(User.last_activity_at < cutoff, User.last_activity_at.is_(None)))
        )
        return int(result.scalar_one())

    async def count_active_current_hour(self) -> int:
        """Users active within the current clock hour (13.4)."""
        start = datetime.datetime.now(datetime.UTC).replace(minute=0, second=0, microsecond=0)
        result = await self.session.execute(
            select(func.count()).select_from(User).where(User.last_activity_at >= start)
        )
        return int(result.scalar_one())

    async def count_active_previous_hour(self) -> int:
        """Users active within the previous clock hour only (13.4)."""
        current = datetime.datetime.now(datetime.UTC).replace(minute=0, second=0, microsecond=0)
        previous = current - datetime.timedelta(hours=1)
        result = await self.session.execute(
            select(func.count())
            .select_from(User)
            .where(User.last_activity_at >= previous, User.last_activity_at < current)
        )
        return int(result.scalar_one())

    async def count_premium(self) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(User).where(User.is_premium.is_(True))
        )
        return int(result.scalar_one())

    async def count_staff(self) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(User).where(User.role.in_(_STAFF_ROLES))
        )
        return int(result.scalar_one())

    @staticmethod
    def _audience_filters(role: str | None, language: str | None) -> list[ColumnElement[bool]]:
        """Broadcast audience filters (16.8, item #14).

        Always excludes banned users. With an explicit ``role`` it targets exactly that
        role; otherwise it targets normal users only — Owner/Moderator are excluded from
        an untargeted broadcast.
        """
        filters: list[ColumnElement[bool]] = [User.is_banned.is_(False)]
        if role is not None:
            filters.append(User.role == role)
        else:
            filters.append(User.role.notin_(_STAFF_ROLES))
        if language is not None:
            filters.append(User.language == language)
        return filters

    async def count_for_broadcast(self, *, role: str | None, language: str | None) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(User).where(*self._audience_filters(role, language))
        )
        return int(result.scalar_one())

    async def count_for_audience(
        self, *, mode: str, rules: Sequence[AudienceRuleSpec], now: datetime.datetime
    ) -> int:
        """Count the broadcast audience defined by a unified expression (Sprint 9.6, D-055)."""
        result = await self.session.execute(
            select(func.count())
            .select_from(User)
            .where(broadcast_audience_predicate(mode, rules, now=now))
        )
        return int(result.scalar_one())

    async def page_for_audience(
        self,
        *,
        after_id: int,
        limit: int,
        mode: str,
        rules: Sequence[AudienceRuleSpec],
        now: datetime.datetime,
    ) -> Sequence[User]:
        """One id-cursor page of the unified-expression audience, ascending (Sprint 9.6)."""
        result = await self.session.execute(
            select(User)
            .where(User.id > after_id, broadcast_audience_predicate(mode, rules, now=now))
            .order_by(User.id.asc())
            .limit(limit)
        )
        return result.scalars().all()

    async def page_for_broadcast(
        self, *, after_id: int, limit: int, role: str | None, language: str | None
    ) -> Sequence[User]:
        result = await self.session.execute(
            select(User)
            .where(User.id > after_id, *self._audience_filters(role, language))
            .order_by(User.id.asc())
            .limit(limit)
        )
        return result.scalars().all()
