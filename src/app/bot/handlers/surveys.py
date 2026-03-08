from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.types import Message

from app.db.repositories.surveys import SurveyRepository
from app.db.repositories.users import UserRepository
from app.db.session import SessionLocal

router = Router()

SURVEY_CMD = re.compile(r"^/survey_(\d+)\s+(.+)$", re.IGNORECASE | re.DOTALL)


@router.message(F.text.regexp(SURVEY_CMD))
async def survey_answer(message: Message):
    match = SURVEY_CMD.match(message.text or "")
    if not match:
        return
    survey_id = int(match.group(1))
    answer = match.group(2).strip()
    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        survey_repo = SurveyRepository(session)
        user = await user_repo.get_by_telegram_id(message.from_user.id)
        survey = await survey_repo.get_by_id(survey_id)
        if not user:
            return
        if not survey or not survey.is_active:
            await message.answer("Опрос не найден или уже закрыт.")
            return
        await survey_repo.add_answer(survey_id=survey_id, user_id=user.id, answer_text=answer)
        await session.commit()
    await message.answer("Спасибо за ответ!")

