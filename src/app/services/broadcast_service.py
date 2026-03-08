from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import BroadcastKindEnum, SegmentEnum
from app.db.repositories.broadcasts import BroadcastRepository
from app.db.repositories.users import UserRepository

logger = logging.getLogger(__name__)


class BroadcastService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()
        self.user_repo = UserRepository(session)
        self.broadcast_repo = BroadcastRepository(session)

    async def create_broadcast(
        self,
        *,
        title: str,
        content: str,
        image_url: str | None,
        target_group: SegmentEnum,
        kind: BroadcastKindEnum = BroadcastKindEnum.broadcast,
        periodic_enabled: bool = False,
        periodic_cron: str | None = None,
        created_by: str | None = None,
    ):
        return await self.broadcast_repo.create(
            title=title,
            content=content,
            image_url=image_url,
            target_group=target_group,
            kind=kind,
            periodic_enabled=periodic_enabled,
            periodic_cron=periodic_cron,
            created_by=created_by,
        )

    async def send_broadcast(self, broadcast_id: int) -> dict[str, int]:
        broadcast = await self.broadcast_repo.get_by_id(broadcast_id)
        if not broadcast:
            raise ValueError("Broadcast not found")
        return await self._send_content(
            segment=broadcast.target_group,
            content=broadcast.content,
            image_url=broadcast.image_url,
            title=broadcast.title,
        )

    async def send_manual(
        self,
        *,
        segment: SegmentEnum,
        title: str,
        content: str,
        image_url: str | None = None,
    ) -> dict[str, int]:
        return await self._send_content(segment=segment, title=title, content=content, image_url=image_url)

    async def _send_content(
        self, *, segment: SegmentEnum, title: str, content: str, image_url: str | None
    ) -> dict[str, int]:
        if not self.settings.bot_token:
            return {"sent": 0, "failed": 0}
        users = await self.user_repo.get_segment_users(segment)
        bot = Bot(self.settings.bot_token)
        sent = 0
        failed = 0
        text = f"{title}\n\n{content}"
        try:
            for user in users:
                try:
                    if image_url:
                        await bot.send_photo(user.telegram_id, image_url, caption=text)
                    else:
                        await bot.send_message(user.telegram_id, text)
                    sent += 1
                except Exception:
                    failed += 1
                    logger.exception("Broadcast failed for telegram_id=%s", user.telegram_id)
                await asyncio.sleep(0.05)
        finally:
            await bot.session.close()
        return {"sent": sent, "failed": failed}

