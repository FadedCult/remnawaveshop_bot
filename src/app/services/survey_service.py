from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.repositories.surveys import SurveyRepository
from app.db.repositories.users import UserRepository

logger = logging.getLogger(__name__)


class SurveyService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()
        self.survey_repo = SurveyRepository(session)
        self.user_repo = UserRepository(session)

    async def create_and_send(self, question: str, created_by: str | None = None):
        survey = await self.survey_repo.create(question=question, created_by=created_by)
        await self.session.flush()
        await self.send_survey(survey.id, question)
        return survey

    async def send_survey(self, survey_id: int, question: str) -> dict[str, int]:
        if not self.settings.bot_token:
            return {"sent": 0, "failed": 0}
        users = await self.user_repo.list_users(limit=200000)
        bot = Bot(self.settings.bot_token)
        sent = 0
        failed = 0
        try:
            for user in users:
                try:
                    await bot.send_message(
                        user.telegram_id,
                        f"📊 Опрос #{survey_id}\n\n{question}\n\nОтветьте командой:\n/survey_{survey_id} ваш_ответ",
                    )
                    sent += 1
                except Exception:
                    failed += 1
                    logger.exception("Survey send failed for telegram_id=%s", user.telegram_id)
                await asyncio.sleep(0.05)
        finally:
            await bot.session.close()
        return {"sent": sent, "failed": failed}

