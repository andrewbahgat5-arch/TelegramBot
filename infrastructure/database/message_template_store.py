"""MessageTemplateStore — session-owning adapter for TemplateService (Sprint 13.8).

``TemplateService`` is a process singleton (it holds an in-memory cache and pushes
i18n overrides), so it must not close over a request-bound session. This adapter
implements the ``MessageTemplateStore`` protocol by opening a short-lived session per
operation on the injected factory — mirroring :class:`AdEventRecorder` (D-052).

``load_all`` / ``get`` return detached, plain row snapshots (not ORM instances) so the
service reads them safely after the session has closed.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from infrastructure.database.repositories.message_template import MessageTemplateRepository


@dataclass(frozen=True, slots=True)
class TemplateRow:
    """A detached snapshot of a ``message_templates`` row."""

    key: str
    locale: str
    content: str
    updated_at: datetime.datetime | None


class MessageTemplateStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def load_all(self) -> Sequence[TemplateRow]:
        async with self._session_factory() as session:
            rows = await MessageTemplateRepository(session).load_all()
            return [TemplateRow(r.key, r.locale, r.content, r.updated_at) for r in rows]

    async def get(self, key: str, locale: str) -> TemplateRow | None:
        async with self._session_factory() as session:
            row = await MessageTemplateRepository(session).get(key, locale)
            if row is None:
                return None
            return TemplateRow(row.key, row.locale, row.content, row.updated_at)

    async def upsert(
        self, key: str, locale: str, content: str, *, updated_by: int | None = None
    ) -> None:
        async with self._session_factory() as session:
            await MessageTemplateRepository(session).upsert(
                key, locale, content, updated_by=updated_by
            )
            await session.commit()

    async def delete_template(self, key: str, locale: str) -> None:
        async with self._session_factory() as session:
            await MessageTemplateRepository(session).delete_template(key, locale)
            await session.commit()
