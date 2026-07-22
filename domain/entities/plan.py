"""Plan domain entity (VERSION_2_MASTER_PLAN §5.1, §6.1).

An immutable, framework-free view of a ``plans`` row. Carries the raw, already-
validated ``entitlements`` mapping; :meth:`entitlements_resolved` projects it to the
typed :class:`ResolvedEntitlements` business logic reads.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from domain.entitlements import ResolvedEntitlements


@dataclass(frozen=True, slots=True)
class Plan:
    """Immutable snapshot of a ``plans`` row."""

    id: int
    code: str
    name: str
    is_active: bool
    sort_order: int
    entitlements: Mapping[str, Any]

    @classmethod
    def from_row(cls, row: Any) -> Plan:
        """Build from a ``plans`` ORM row (attribute access only)."""
        return cls(
            id=row.id,
            code=row.code,
            name=row.name,
            is_active=row.is_active,
            sort_order=row.sort_order,
            entitlements=dict(row.entitlements),
        )

    def entitlements_resolved(self) -> ResolvedEntitlements:
        """The typed entitlements for this plan (validated at load time)."""
        return ResolvedEntitlements.from_mapping(self.entitlements)
