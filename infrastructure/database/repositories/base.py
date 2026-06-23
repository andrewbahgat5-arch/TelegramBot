"""Generic SQLAlchemy repository (MASTER_PLAN Task 2.7, Component 9.5).

Provides the common CRUD surface (``add``, ``get_by_id``, ``list_paginated``,
``delete``). Concrete repositories subclass this, set ``model`` and (if the lookup
column is not ``id``) ``id_attr``, and add entity-specific queries. Repositories
never commit — they ``add``/``flush`` only — so the caller owns the transaction
boundary.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from infrastructure.database.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class SqlAlchemyRepository(Generic[ModelT]):
    """Base async repository over a single ORM model.

    The lookup column is resolved via ``getattr`` rather than stored as a class
    attribute: storing an ``InstrumentedAttribute`` directly would trigger the
    descriptor protocol on access (this class is not a mapped entity).
    """

    model: ClassVar[type[Base]]
    id_attr: ClassVar[str] = "id"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @property
    def _id_column(self) -> InstrumentedAttribute[Any]:
        column: InstrumentedAttribute[Any] = getattr(self.model, self.id_attr)
        return column

    async def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def get_by_id(self, id_: Any) -> ModelT | None:
        result = await self.session.execute(
            select(self.model).where(self._id_column == id_).limit(1)
        )
        return result.scalar_one_or_none()  # type: ignore[return-value]

    async def list_paginated(self, *, limit: int = 50, offset: int = 0) -> Sequence[ModelT]:
        result = await self.session.execute(
            select(self.model).order_by(self._id_column).limit(limit).offset(offset)
        )
        return result.scalars().all()  # type: ignore[return-value]

    async def delete(self, entity: ModelT) -> None:
        await self.session.delete(entity)
        await self.session.flush()
