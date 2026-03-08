from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import Select, String, cast, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    PaymentLog,
    SegmentEnum,
    Subscription,
    SubscriptionStatusEnum,
    SurveyAnswer,
    Ticket,
    TicketMessage,
    User,
)


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        query: Select[tuple[User]] = select(User).where(User.telegram_id == telegram_id)
        return await self.session.scalar(query)

    async def upsert_telegram_user(
        self, telegram_id: int, username: str | None, full_name: str | None, is_admin: bool = False
    ) -> User:
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            user.username = username
            user.full_name = full_name
            user.is_admin = is_admin or user.is_admin
            await self.session.flush()
            return user
        user = User(
            telegram_id=telegram_id,
            username=username,
            full_name=full_name,
            is_admin=is_admin,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def list_users(self, search: str | None = None, limit: int = 50, offset: int = 0) -> list[User]:
        query = select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
        if search:
            like = f"%{search}%"
            query = query.where(
                or_(
                    User.username.ilike(like),
                    User.full_name.ilike(like),
                    cast(User.telegram_id, String).ilike(like),
                )
            )
        result = await self.session.scalars(query)
        return list(result)

    async def count_all(self) -> int:
        return int(await self.session.scalar(select(func.count()).select_from(User)) or 0)

    async def count_new_for_days(self, days: int = 7) -> int:
        start = datetime.now(timezone.utc) - timedelta(days=days)
        query = select(func.count()).select_from(User).where(User.created_at >= start)
        return int(await self.session.scalar(query) or 0)

    async def count_active_subscribers(self) -> int:
        now = datetime.now(timezone.utc)
        query = (
            select(func.count(func.distinct(User.id)))
            .select_from(User)
            .join(Subscription, Subscription.user_id == User.id)
            .where(
                Subscription.status == SubscriptionStatusEnum.active,
                Subscription.end_at.is_not(None),
                Subscription.end_at > now,
            )
        )
        return int(await self.session.scalar(query) or 0)

    async def get_segment_users(self, segment: SegmentEnum) -> list[User]:
        now = datetime.now(timezone.utc)
        active_subquery = (
            select(Subscription.user_id)
            .where(
                Subscription.status == SubscriptionStatusEnum.active,
                Subscription.end_at.is_not(None),
                Subscription.end_at > now,
            )
            .subquery()
        )
        if segment == SegmentEnum.all:
            query = select(User)
        elif segment == SegmentEnum.with_subscription:
            query = select(User).where(User.id.in_(select(active_subquery.c.user_id)))
        else:
            query = select(User).where(~User.id.in_(select(active_subquery.c.user_id)))
        users = await self.session.scalars(query)
        return list(users)

    async def set_language(self, user: User, language: str) -> None:
        user.language = language  # type: ignore[assignment]
        await self.session.flush()

    async def adjust_balance(self, user: User, amount: Decimal) -> User:
        user.balance = (user.balance or Decimal("0.00")) + amount
        await self.session.flush()
        return user

    async def delete_user(self, user: User) -> None:
        ticket_ids = select(Ticket.id).where(Ticket.user_id == user.id)
        await self.session.execute(delete(TicketMessage).where(TicketMessage.ticket_id.in_(ticket_ids)))
        await self.session.execute(delete(Ticket).where(Ticket.user_id == user.id))
        await self.session.execute(delete(Subscription).where(Subscription.user_id == user.id))
        await self.session.execute(delete(SurveyAnswer).where(SurveyAnswer.user_id == user.id))
        await self.session.execute(delete(PaymentLog).where(PaymentLog.user_id == user.id))
        await self.session.delete(user)
        await self.session.flush()
