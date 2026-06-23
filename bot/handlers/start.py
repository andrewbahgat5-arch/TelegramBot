"""/start handler (MASTER_PLAN Task 4.8).

Minimal handler that proves the pipeline (auth → throttle → handler). No business
logic: it greets the already-resolved user. Copy is V1 English; i18n arrives in V2.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from domain.entities.user import UserSnapshot

router = Router(name="start")

_WELCOME = (
    "👋 Welcome{name}!\n\n"
    "Send me a link to a video or audio post and I'll fetch it for you.\n"
    "Use /help to see what I can do."
)


@router.message(CommandStart())
async def handle_start(message: Message, user: UserSnapshot | None = None) -> None:
    name = f", {user.first_name}" if user and user.first_name else ""
    await message.answer(_WELCOME.format(name=name))
