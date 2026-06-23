"""UserRepository (MASTER_PLAN 10.2, D-012)."""

from __future__ import annotations

import datetime

from sqlalchemy import select, update

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
