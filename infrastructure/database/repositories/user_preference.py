"""UserPreferenceRepository (MASTER_PLAN 10.13)."""

from __future__ import annotations

from sqlalchemy import select

from infrastructure.database.models import UserPreference
from infrastructure.database.repositories.base import SqlAlchemyRepository


class UserPreferenceRepository(SqlAlchemyRepository[UserPreference]):
    model = UserPreference

    async def get_by_user_id(self, user_id: int) -> UserPreference | None:
        result = await self.session.execute(
            select(UserPreference).where(UserPreference.user_id == user_id)
        )
        return result.scalar_one_or_none()
