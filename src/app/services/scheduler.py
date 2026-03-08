from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.broadcasts import BroadcastRepository
from app.services.broadcast_service import BroadcastService

logger = logging.getLogger(__name__)


class AppScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started")

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")

    def register_periodic_promo_job(self, session_factory) -> None:
        self.scheduler.add_job(
            self._run_periodic_promos,
            trigger="interval",
            minutes=1,
            kwargs={"session_factory": session_factory},
            id="periodic_promos",
            replace_existing=True,
        )

    async def _run_periodic_promos(self, session_factory) -> None:
        async with session_factory() as session:  # type: AsyncSession
            repo = BroadcastRepository(session)
            service = BroadcastService(session)
            broadcasts = await repo.list_periodic_enabled()
            now = datetime.now(timezone.utc)
            for item in broadcasts:
                interval_min = self._cron_to_minutes(item.periodic_cron)
                if item.last_sent_at and now - item.last_sent_at < timedelta(minutes=interval_min):
                    continue
                try:
                    result = await service.send_manual(
                        segment=item.target_group,
                        title=item.title,
                        content=item.content,
                        image_url=item.image_url,
                    )
                    await repo.mark_sent(item)
                    logger.info("Periodic promo sent id=%s result=%s", item.id, result)
                except Exception:
                    logger.exception("Periodic promo failed id=%s", item.id)
            await session.commit()

    @staticmethod
    def _cron_to_minutes(periodic_cron: str | None) -> int:
        """
        Lightweight mode: `periodic_cron` is interpreted as integer minutes.
        """
        if not periodic_cron:
            return 1440
        try:
            value = int(periodic_cron)
            return max(value, 1)
        except ValueError:
            return 1440

