from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Subscription, SubscriptionStatusEnum


class SubscriptionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, subscription_id: int) -> Subscription | None:
        return await self.session.get(Subscription, subscription_id)

    async def get_latest_for_user(self, user_id: int) -> Subscription | None:
        query = (
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .order_by(desc(Subscription.created_at))
            .limit(1)
        )
        return await self.session.scalar(query)

    async def get_active_for_user(self, user_id: int) -> Subscription | None:
        now = datetime.now(timezone.utc)
        query = (
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.status == SubscriptionStatusEnum.active,
                Subscription.end_at.is_not(None),
                Subscription.end_at > now,
            )
            .order_by(desc(Subscription.end_at))
            .limit(1)
        )
        return await self.session.scalar(query)

    async def create(self, subscription: Subscription) -> Subscription:
        self.session.add(subscription)
        await self.session.flush()
        return subscription

    async def deactivate_all(self, user_id: int) -> None:
        now = datetime.now(timezone.utc)
        rows = await self.session.scalars(
            select(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.status == SubscriptionStatusEnum.active,
            )
        )
        for item in rows:
            item.status = SubscriptionStatusEnum.expired
            if item.end_at is None:
                item.end_at = now
        await self.session.flush()

