"""UserRepository (MASTER_PLAN 10.2, D-012)."""

from __future__ import annotations

import datetime
from collections.abc import Sequence

from sqlalchemy import case, func, select, update
from sqlalchemy.sql.elements import ColumnElement

from infrastructure.database.models import User
from infrastructure.database.repositories.base import SqlAlchemyRepository


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

    @staticmethod
    def _audience_filters(role: str | None, language: str | None) -> list[ColumnElement[bool]]:
        """Broadcast audience = non-banned users matching the optional role/language."""
        filters: list[ColumnElement[bool]] = [User.is_banned.is_(False)]
        if role is not None:
            filters.append(User.role == role)
        if language is not None:
            filters.append(User.language == language)
        return filters

    async def count_for_broadcast(self, *, role: str | None, language: str | None) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(User).where(*self._audience_filters(role, language))
        )
        return int(result.scalar_one())

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
