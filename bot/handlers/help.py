"""/help handler (MASTER_PLAN Task 4.8).

Minimal handler that proves the pipeline. No business logic. Copy is V1 English.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router(name="help")

_HELP = (
    "<b>How to use this bot</b>\n\n"
    "• Send a supported link and pick a format/quality to download.\n"
    "• /start — restart the bot.\n"
    "• /help — show this message."
)


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    await message.answer(_HELP)
