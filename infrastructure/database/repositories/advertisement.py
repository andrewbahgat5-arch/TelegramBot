"""AdRepository (MASTER_PLAN 10.10)."""

from __future__ import annotations

from infrastructure.database.models import Advertisement
from infrastructure.database.repositories.base import SqlAlchemyRepository


class AdRepository(SqlAlchemyRepository[Advertisement]):
    model = Advertisement
