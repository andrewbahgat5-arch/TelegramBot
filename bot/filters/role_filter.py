"""RoleFilter (MASTER_PLAN Component 9.1, Task 4.7).

Declarative role gating for handlers. ``AuthMiddleware`` attaches the resolved
:class:`UserSnapshot` as ``data["user"]``; aiogram injects it into the filter by
name. Authorization rules live here and in ``UserService`` — never in handlers
(Section 9.1, ``AdminHandlers`` "Must Never Modify").
"""

from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from domain.entities.user import UserSnapshot
from domain.enums import UserRole


class RoleFilter(BaseFilter):
    """Pass only when the current user holds one of ``roles``."""

    def __init__(self, *roles: UserRole) -> None:
        self._roles = frozenset(roles)

    async def __call__(self, event: TelegramObject, user: UserSnapshot | None = None) -> bool:
        return user is not None and user.role in self._roles


# Convenience: staff = owner or moderator (Section 9.1 admin surface).
StaffFilter = RoleFilter(UserRole.OWNER, UserRole.MODERATOR)
