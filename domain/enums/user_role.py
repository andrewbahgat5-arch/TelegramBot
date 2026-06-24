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


# Roles exempt from ALL download quotas, cooldowns, message throttling, and the
# single-active-job cap (#21). The Owner is unlimited. This is the single place that
# decides "no limits apply" — extend it when premium/admin tiers gain their own
# role-specific policies (#22). ``StrEnum`` members compare equal to their string
# value, so ``row.role in UNLIMITED_ROLES`` works for both the DB string and the enum.
UNLIMITED_ROLES: frozenset[UserRole] = frozenset({UserRole.OWNER})
