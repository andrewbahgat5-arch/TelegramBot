"""Panel action registry (Sprint 9.6, F-2 / EP-22).

The single source of truth for panel action codes and their authorization tier,
so the :class:`~bot.filters.panel_filter.PanelFilter` and the keyboard builders
agree and new sections / future plugins extend exactly one place.

Tier rule (security-first): an action is **READ** (staff-visible: owner *and*
moderator) only if it is explicitly listed here; *everything else* — every
mutation, every destructive-confirm screen, every wizard step — defaults to
**WRITE** (owner-only). Forgetting to list a new action therefore fails safe
(denied to moderators), never the reverse. This pairs with hiding write buttons
from moderators in the keyboard layer (defense in depth, MASTER_PLAN §9.1 — authz
never decided in handler bodies).

Action codes are short, opaque tokens carried in the signed ``P`` callback
(``bot/callbacks/factory.py``). Read/navigation codes only *open menus, page
lists, and view details* — never an affordance that mutates without a further
owner-gated press (so an "open delete-confirm" screen is WRITE, not READ).
"""

from __future__ import annotations

# Read / navigation actions. Non-mutating and lead to no mutation on their own.
READ_ACTIONS: frozenset[str] = frozenset(
    {
        "op",  # open a section menu / submenu
        "bk",  # back to the parent menu
        "hm",  # home — the root admin panel
        "pg",  # paginate a list
        "ls",  # (re-)render a list
        "inf",  # view an entity detail (user info, ad stats, system status, …)
        "cx",  # cancel / abort a wizard (non-mutating; returns to a menu)
    }
)


def is_write_action(action: str) -> bool:
    """True if ``action`` mutates state or leads to one (owner-only tier).

    Unknown codes are treated as WRITE so an unregistered action fails safe.
    """
    return action not in READ_ACTIONS
