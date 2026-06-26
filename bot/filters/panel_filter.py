"""PanelFilter (Sprint 9.6, F-2 / EP-22).

Declarative gating + parsing for admin-panel callbacks, mirroring how
:class:`~bot.filters.role_filter.RoleFilter` keeps authorization out of handler
bodies (MASTER_PLAN §9.1). The filter:

* matches only data in the signed ``P`` namespace (``bot/callbacks/factory.py``);
* verifies the HMAC signature — forged / garbled data fails the check and the
  filter returns ``False`` (no handler matches → silently ignored, §14.2);
* classifies the action read vs write via :mod:`bot.panel.registry`, matching
  only when the action's tier equals the requested ``mutating`` flag; and
* on a match, injects the verified :class:`ParsedPanel` into the handler context
  as ``panel`` — so handlers never parse or re-verify callback data.

Registration pairs the tier filter with a role filter (defense in depth on top of
hiding write buttons from moderators):

    @router.callback_query(PanelFilter(mutating=False), StaffFilter)   # read
    @router.callback_query(PanelFilter(mutating=True), OwnerFilter)    # write

``callback_signer`` is resolved from the dispatcher workflow data by name, exactly
as ``RoleFilter`` resolves ``user`` (both are part of the propagated context).
"""

from __future__ import annotations

from typing import Any

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, TelegramObject

from bot.callbacks.factory import CallbackSigner
from bot.panel.registry import is_write_action

_PANEL_PREFIX = "P|"


class PanelFilter(BaseFilter):
    """Match a signed panel callback of the requested authorization tier."""

    def __init__(self, *, mutating: bool) -> None:
        self._mutating = mutating

    async def __call__(
        self, event: TelegramObject, callback_signer: CallbackSigner
    ) -> bool | dict[str, Any]:
        if not isinstance(event, CallbackQuery):
            return False
        data = event.data or ""
        if not data.startswith(_PANEL_PREFIX):
            return False
        parsed = callback_signer.unpack_panel(data)
        if parsed is None:
            return False
        if is_write_action(parsed.action) != self._mutating:
            return False
        return {"panel": parsed}
