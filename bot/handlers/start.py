"""/start handler (MASTER_PLAN Task 4.8 + Sprint 9.5 home placement).

Greets the already-resolved user, then runs the best-effort ``home`` ad placement
(no-op unless the Owner has enabled ``ad_placement_home_enabled``). No business logic
beyond delegating to ``AdService`` (Section 9.1). Copy is V1 English; i18n arrives in V2.
"""

from __future__ import annotations

from collections.abc import Callable

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.ads import show_placement_ad
from domain.entities.user import UserSnapshot
from domain.enums import AdPlacement
from services.ad_service import AdService

router = Router(name="start")

_WELCOME = (
    "👋 Welcome{name}!\n\n"
    "Send me a link to a video or audio post and I'll fetch it for you.\n"
    "Use /help to see what I can do."
)


@router.message(CommandStart())
async def handle_start(
    message: Message,
    user: UserSnapshot | None = None,
    session: AsyncSession | None = None,
    ad_service_factory: Callable[[AsyncSession], AdService] | None = None,
) -> None:
    name = f", {user.first_name}" if user and user.first_name else ""
    await message.answer(_WELCOME.format(name=name))
    if user is not None and session is not None and ad_service_factory is not None:
        await show_placement_ad(ad_service_factory(session), user, AdPlacement.HOME.value)
