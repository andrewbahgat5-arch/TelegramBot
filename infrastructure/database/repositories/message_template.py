"""MessageTemplateRepository (Sprint 13.8)."""

from __future__ import annotations

import datetime
from collections.abc import Sequence

from sqlalchemy import delete, select, update

from infrastructure.database.models import MessageTemplate
from infrastructure.database.repositories.base import SqlAlchemyRepository


class MessageTemplateRepository(SqlAlchemyRepository[MessageTemplate]):
    model = MessageTemplate

    async def load_all(self) -> Sequence[MessageTemplate]:
        """Every custom template row (warms the TemplateService cache at startup)."""
        result = await self.session.execute(select(MessageTemplate))
        return result.scalars().all()

    async def get(self, key: str, locale: str) -> MessageTemplate | None:
        result = await self.session.execute(
            select(MessageTemplate).where(
                MessageTemplate.key == key, MessageTemplate.locale == locale
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self, key: str, locale: str, content: str, *, updated_by: int | None = None
    ) -> None:
        """Insert or update a custom template on the ``(key, locale)`` primary key."""
        now = datetime.datetime.now(datetime.UTC)
        existing = await self.get(key, locale)
        if existing is None:
            self.session.add(
                MessageTemplate(
                    key=key,
                    locale=locale,
                    content=content,
                    is_custom=True,
                    updated_by=updated_by,
                    updated_at=now,
                )
            )
        else:
            await self.session.execute(
                update(MessageTemplate)
                .where(MessageTemplate.key == key, MessageTemplate.locale == locale)
                .values(content=content, is_custom=True, updated_by=updated_by, updated_at=now)
            )
        await self.session.flush()

    async def set_buttons(
        self, key: str, locale: str, buttons: list[dict[str, str]] | None
    ) -> None:
        """Update the buttons JSONB column for a template."""
        existing = await self.get(key, locale)
        if existing is not None:
            await self.session.execute(
                update(MessageTemplate)
                .where(MessageTemplate.key == key, MessageTemplate.locale == locale)
                .values(buttons=buttons)
            )
            await self.session.flush()

    async def delete_template(self, key: str, locale: str) -> None:
        """Remove a custom template (revert to the shipped i18n default)."""
        await self.session.execute(
            delete(MessageTemplate).where(
                MessageTemplate.key == key, MessageTemplate.locale == locale
            )
        )
        await self.session.flush()
