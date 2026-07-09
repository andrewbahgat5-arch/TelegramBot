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

    _FLAG_FIELDS = frozenset({"auto_download_small", "hide_title"})

    async def set_flag(self, user_id: int, field: str, value: bool) -> None:
        """Set one boolean preference, creating the row on first write (upsert)."""
        if field not in self._FLAG_FIELDS:
            raise ValueError(f"unknown preference flag: {field}")
        row = await self.get_by_user_id(user_id)
        if row is None:
            row = UserPreference(user_id=user_id)
            self.session.add(row)
        setattr(row, field, value)
        await self.session.flush()
