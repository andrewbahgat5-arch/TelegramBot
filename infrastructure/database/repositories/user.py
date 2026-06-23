"""UserRepository (MASTER_PLAN 10.2, D-012)."""

from __future__ import annotations

import datetime

from sqlalchemy import select

from infrastructure.database.models import User
from infrastructure.database.repositories.base import SqlAlchemyRepository


class UserRepository(SqlAlchemyRepository[User]):
    model = User

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

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
