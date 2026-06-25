"""AdButtonRepository (MASTER_PLAN Sprint 9.5, D-042)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, select, update

from infrastructure.database.models import AdButton
from infrastructure.database.repositories.base import SqlAlchemyRepository


class AdButtonRepository(SqlAlchemyRepository[AdButton]):
    model = AdButton

    async def list_for_ad(self, ad_id: int) -> Sequence[AdButton]:
        result = await self.session.execute(
            select(AdButton)
            .where(AdButton.advertisement_id == ad_id)
            .order_by(AdButton.row.asc(), AdButton.position.asc(), AdButton.id.asc())
        )
        return result.scalars().all()

    async def create_button(
        self, *, advertisement_id: int, text: str, url: str | None, row: int, position: int
    ) -> AdButton:
        button = AdButton(
            advertisement_id=advertisement_id, text=text, url=url, row=row, position=position
        )
        return await self.add(button)

    async def delete_for_ad(self, ad_id: int) -> int:
        result = await self.session.execute(
            delete(AdButton).where(AdButton.advertisement_id == ad_id)
        )
        await self.session.flush()
        return result.rowcount or 0

    async def increment_clicks(self, button_id: int) -> None:
        await self.session.execute(
            update(AdButton).where(AdButton.id == button_id).values(clicks=AdButton.clicks + 1)
        )
        await self.session.flush()
