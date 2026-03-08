from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Survey, SurveyAnswer


class SurveyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, question: str, created_by: str | None = None) -> Survey:
        survey = Survey(question=question, created_by=created_by)
        self.session.add(survey)
        await self.session.flush()
        return survey

    async def list_all(self) -> list[Survey]:
        rows = await self.session.scalars(
            select(Survey).options(selectinload(Survey.answers)).order_by(desc(Survey.created_at))
        )
        return list(rows)

    async def get_active(self) -> list[Survey]:
        rows = await self.session.scalars(select(Survey).where(Survey.is_active.is_(True)))
        return list(rows)

    async def get_by_id(self, survey_id: int) -> Survey | None:
        query = select(Survey).where(Survey.id == survey_id).options(selectinload(Survey.answers))
        return await self.session.scalar(query)

    async def add_answer(self, survey_id: int, user_id: int, answer_text: str) -> SurveyAnswer:
        answer = SurveyAnswer(survey_id=survey_id, user_id=user_id, answer_text=answer_text)
        self.session.add(answer)
        await self.session.flush()
        return answer

    async def close(self, survey: Survey) -> Survey:
        survey.is_active = False
        await self.session.flush()
        return survey

