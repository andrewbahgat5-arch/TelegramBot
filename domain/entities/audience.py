"""Audience targeting value objects (Sprint 9.6, F-2 / EP-22).

See ``DESIGN_9.6_unified_audience_wizard.md``. A transport-free representation of an
audience rule, shared by the two evaluators that MUST agree (design invariant #17):

* the per-viewer **Python matcher** (``services.audience_service.evaluate_audience``),
  used on the ad-delivery path (one viewer at a time); and
* the set-based **SQL compiler** (``infrastructure.database.audience_query``), used to
  count and page a broadcast audience (many users at once).

``AudienceRuleSpec`` carries the same three fields as an ``ad_audience_rules`` row
(``effect`` / ``dimension`` / ``value``), so either an ORM row or a spec can be fed to
the matcher — it reads only those attributes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AudienceRuleSpec:
    """One audience rule: an ``effect`` (include/exclude) on a ``dimension`` ``value``."""

    effect: str
    dimension: str
    value: str
