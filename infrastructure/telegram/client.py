"""Telegram ``Bot`` factory (MASTER_PLAN Task 6.3 / 6.7, D-040).

Builds the aiogram ``Bot`` used by both the bot and worker composition roots. When
``BOT_API_BASE_URL`` is set, the client targets a self-hosted Telegram Bot API
server (2 GB upload cap); otherwise it uses the public api.telegram.org (50 MB).
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

from core.config import Settings


def build_bot(settings: Settings) -> Bot:
    session: AiohttpSession | None = None
    if settings.use_local_bot_api:
        session = AiohttpSession(api=TelegramAPIServer.from_base(settings.bot_api_base_url))
    return Bot(
        token=settings.bot_token.get_secret_value(),
        session=session,
        default=DefaultBotProperties(parse_mode=settings.bot_parse_mode),
    )
