"""BroadcastRepository (MASTER_PLAN 10.9)."""

from __future__ import annotations

from infrastructure.database.models import Broadcast
from infrastructure.database.repositories.base import SqlAlchemyRepository


class BroadcastRepository(SqlAlchemyRepository[Broadcast]):
    model = Broadcast
