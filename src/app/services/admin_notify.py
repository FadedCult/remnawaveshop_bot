from __future__ import annotations

import logging

from aiogram import Bot

from app.config import get_settings

logger = logging.getLogger(__name__)


async def notify_admins(text: str) -> None:
    settings = get_settings()
    if not settings.bot_token or not settings.bot_admin_ids:
        return
    bot = Bot(settings.bot_token)
    try:
        for admin_id in settings.bot_admin_ids:
            try:
                await bot.send_message(admin_id, text)
            except Exception:
                logger.exception("Failed to notify admin_id=%s", admin_id)
    finally:
        await bot.session.close()

