"""Admin panel FSM states (Sprint 9.6, F-2 / EP-22).

Guided text-input flows for the inline panel. aiogram's default ``MemoryStorage``
backs these (no new Redis key — §11.4 stays locked); state is per (chat, user) and
short-lived, which is fine for single-process admin wizards. Any panel navigation
or write clears pending input, so only one guided input is ever active at a time
(busy-state protection).

* :attr:`setting_value` — the Owner is typing a new value for a numeric setting
  (the "Enter Value" alternative to the minus/plus stepper, 9.6.7).
* :attr:`user_lookup` — staff is typing a Telegram id for User Info (9.6.8).
* :attr:`wizard_text` — the Owner is typing a wizard value (internal name / notes /
  language / user id / button), discriminated by ``field`` in the FSM data (9.6 wizard).
* :attr:`wizard_content` — the Owner is sending the advertisement content; the next
  message becomes the ad (copy-mode capture, 9.6 wizard).
"""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class PanelStates(StatesGroup):
    setting_value = State()
    user_lookup = State()
    wizard_text = State()
    wizard_content = State()
