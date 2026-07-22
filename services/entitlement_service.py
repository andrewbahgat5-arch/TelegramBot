"""EntitlementService — the ONLY entitlement read path (VERSION_2_MASTER_PLAN §5.1).

Two pieces:

* :class:`PlanCatalog` — the in-process, startup-validated set of plans. Every plan's
  ``entitlements`` JSONB is validated against the registry at load; an invalid plan fails
  boot (``EntitlementError``), the same fail-fast as the locale-catalog guard. Rare plan
  edits refresh it (a ``plans:version`` bump, wired in a later sprint).
* :class:`EntitlementService` — pure resolution: given a user's active subscription (or
  ``None``), return the effective plan + entitlements, evaluating expiry lazily (V2-D-007).
  No DB access here, so it is trivially unit-testable against the parity matrix; the caller
  fetches the active row and passes it in.

Business logic reads ``ResolvedPlan.entitlements.<field>`` only — never ``is_premium``,
never a plan-code branch (V2-D-005).
"""

from __future__ import annotations

import datetime
from collections.abc import Iterable
from dataclasses import dataclass

from domain.entities.plan import Plan
from domain.entities.subscription import Subscription
from domain.entitlements import EntitlementError, ResolvedEntitlements, validate

_FREE_PLAN_CODE = "free"


@dataclass(frozen=True, slots=True)
class ResolvedPlan:
    """A user's effective plan code + typed entitlements."""

    plan_code: str
    entitlements: ResolvedEntitlements


class PlanCatalog:
    """Startup-validated, in-process view of all plans (keyed by code and id)."""

    def __init__(self, plans: Iterable[Plan]) -> None:
        by_code: dict[str, Plan] = {}
        by_id: dict[int, Plan] = {}
        for plan in plans:
            validate(plan.code, plan.entitlements)  # fail-fast on a malformed plan
            by_code[plan.code] = plan
            by_id[plan.id] = plan
        if _FREE_PLAN_CODE not in by_code:
            raise EntitlementError(
                f"no {_FREE_PLAN_CODE!r} plan found — the resolver's default plan is required"
            )
        self._by_code = by_code
        self._by_id = by_id

    @property
    def free(self) -> Plan:
        return self._by_code[_FREE_PLAN_CODE]

    def by_id(self, plan_id: int) -> Plan | None:
        return self._by_id.get(plan_id)

    def by_code(self, code: str) -> Plan | None:
        return self._by_code.get(code)


class EntitlementService:
    """Resolves a user's effective entitlements from their active subscription."""

    def __init__(self, catalog: PlanCatalog) -> None:
        self._catalog = catalog

    def resolve(
        self, active: Subscription | None, *, now: datetime.datetime
    ) -> ResolvedPlan:
        """Effective plan for a user: their active-and-unexpired subscription's plan, else Free.

        Expiry is evaluated here, lazily (V2-D-007) — an ``active`` row past ``expires_at``
        degrades to Free without waiting for the hygiene job. A dangling ``plan_id`` (plan
        row deleted) also falls back to Free rather than raising on the hot path.
        """
        plan = self._catalog.free
        if active is not None and active.is_active_at(now):
            plan = self._catalog.by_id(active.plan_id) or self._catalog.free
        return ResolvedPlan(plan_code=plan.code, entitlements=plan.entitlements_resolved())
