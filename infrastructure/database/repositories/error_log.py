"""ErrorLogRepository (MASTER_PLAN 10.12, partitioned)."""

from __future__ import annotations

from infrastructure.database.models import ErrorLog
from infrastructure.database.repositories.base import SqlAlchemyRepository


class ErrorLogRepository(SqlAlchemyRepository[ErrorLog]):
    model = ErrorLog
