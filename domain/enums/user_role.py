"""User roles (MASTER_PLAN 10.2: ``users.role``)."""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """Authorization role for a user.

    Persisted as the ``users.role`` VARCHAR(20) column; default ``user``.
    """

    OWNER = "owner"
    MODERATOR = "moderator"
    USER = "user"

    @property
    def is_staff(self) -> bool:
        """Owner and Moderator are privileged (admin surface)."""
        return self in (UserRole.OWNER, UserRole.MODERATOR)
