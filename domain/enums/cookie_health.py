"""Cookie health states (DESIGN_COOKIE_POOL.md §7).

Five states, exactly as approved. **Cooldown is deliberately NOT a state** — it is an
orthogonal ``cooldown_until`` timestamp on the row. Modelling it as a sixth state would
make "expired but cooling down" representable and force every query to special-case it.

Only ``HEALTHY`` and ``WARNING`` are selectable, and only when no cooldown is active.
"""

from __future__ import annotations

from enum import StrEnum


class CookieHealth(StrEnum):
    # Selectable
    HEALTHY = "healthy"
    WARNING = "warning"  # recent auth failures; usable but deprioritised
    # Not selectable — need a human or a recovery probe
    EXPIRED = "expired"  # session no longer accepted; a probe may revive it
    INVALID = "invalid"  # malformed file / terminated account; replace only
    DISABLED = "disabled"  # switched off by an admin; never auto-selected


#: States the selector may hand out (subject to the cooldown check).
SELECTABLE_HEALTH: frozenset[CookieHealth] = frozenset(
    {CookieHealth.HEALTHY, CookieHealth.WARNING}
)

#: Terminal states that trigger an immediate Owner/Moderator notification (§9).
NOTIFY_HEALTH: frozenset[CookieHealth] = frozenset(
    {CookieHealth.EXPIRED, CookieHealth.INVALID, CookieHealth.DISABLED}
)

#: States a background probe may attempt to recover. INVALID (broken file) and
#: DISABLED (a deliberate human decision) are never auto-probed.
RECOVERABLE_HEALTH: frozenset[CookieHealth] = frozenset({CookieHealth.EXPIRED})
