"""/help handler (MASTER_PLAN Task 4.8, Sprint 11.5 i18n).

Minimal handler that proves the pipeline. No business logic.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from core.i18n import Translator

router = Router(name="help")


@router.message(Command("help"))
async def handle_help(message: Message, translate: Translator, locale: str) -> None:
    await message.answer(translate("help.body", locale))
