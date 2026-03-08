from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Subscription, SubscriptionStatusEnum, Tariff, User
from app.db.repositories.subscriptions import SubscriptionRepository
from app.exceptions import BusinessLogicError, RemnawaveAPIError
from app.services.admin_notify import notify_admins
from app.services.remnawave import RemnawaveClient

logger = logging.getLogger(__name__)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


class SubscriptionService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.remnawave = RemnawaveClient()
        self.sub_repo = SubscriptionRepository(session)

    async def ensure_remote_user(self, user: User) -> str:
        if user.remnawave_user_id:
            return user.remnawave_user_id
        try:
            found = await self.remnawave.find_user_by_external_id(user.telegram_id)
            if found and found.get("id"):
                user.remnawave_user_id = str(found["id"])
                await self.session.flush()
                return user.remnawave_user_id
            created = await self.remnawave.create_user(user.telegram_id, user.username, user.full_name)
            user_id = created.get("id") or (created.get("data") or {}).get("id")
            if not user_id:
                raise RemnawaveAPIError("Missing user id in Remnawave create_user response", payload=created)
            user.remnawave_user_id = str(user_id)
            await self.session.flush()
            return user.remnawave_user_id
        except RemnawaveAPIError:
            logger.exception("Failed to ensure remote user for telegram_id=%s", user.telegram_id)
            await notify_admins(
                f"⚠️ Ошибка Remnawave при создании пользователя TG:{user.telegram_id}. Проверьте API."
            )
            raise

    async def get_active_subscription(self, user_id: int) -> Subscription | None:
        return await self.sub_repo.get_active_for_user(user_id)

    async def buy_subscription(self, user: User, tariff: Tariff) -> Subscription:
        if user.balance < tariff.price:
            raise BusinessLogicError("Недостаточно средств на балансе")
        remote_user_id = await self.ensure_remote_user(user)
        try:
            remote = await self.remnawave.create_subscription(
                remote_user_id,
                plan_id=tariff.remnawave_plan_id,
                duration_days=tariff.duration_days,
                traffic_limit_gb=tariff.traffic_limit_gb,
            )
        except RemnawaveAPIError:
            logger.exception("Failed to create subscription in Remnawave for user_id=%s", user.id)
            await notify_admins(f"⚠️ Ошибка Remnawave при оформлении подписки для TG:{user.telegram_id}.")
            raise

        remote_data = remote.get("data") if isinstance(remote.get("data"), dict) else remote
        remote_subscription_id = str(remote_data.get("id")) if remote_data.get("id") else None
        start_at = _parse_datetime(remote_data.get("start_at")) or datetime.now(timezone.utc)
        end_at = _parse_datetime(remote_data.get("end_at")) or (
            datetime.now(timezone.utc) + timedelta(days=tariff.duration_days)
        )
        connect_url = remote_data.get("connect_url")
        if not connect_url and remote_subscription_id:
            connect_url = await self.remnawave.get_connect_link(remote_subscription_id)

        await self.sub_repo.deactivate_all(user.id)
        subscription = Subscription(
            user_id=user.id,
            tariff_id=tariff.id,
            status=SubscriptionStatusEnum.active,
            start_at=start_at,
            end_at=end_at,
            traffic_limit_gb=tariff.traffic_limit_gb,
            remnawave_subscription_id=remote_subscription_id,
            connect_url=connect_url,
        )
        await self.sub_repo.create(subscription)
        user.balance = user.balance - Decimal(tariff.price)
        await self.session.flush()
        return subscription

    async def extend_subscription(self, user: User, subscription: Subscription, tariff: Tariff) -> Subscription:
        if user.balance < tariff.price:
            raise BusinessLogicError("Недостаточно средств на балансе")
        if not subscription.remnawave_subscription_id:
            raise BusinessLogicError("Невозможно продлить подписку: не найден remote ID")
        try:
            remote = await self.remnawave.extend_subscription(
                subscription.remnawave_subscription_id,
                duration_days=tariff.duration_days,
            )
        except RemnawaveAPIError:
            logger.exception("Failed to extend subscription for user_id=%s", user.id)
            await notify_admins(f"⚠️ Ошибка Remnawave при продлении подписки для TG:{user.telegram_id}.")
            raise

        remote_data = remote.get("data") if isinstance(remote.get("data"), dict) else remote
        end_at = _parse_datetime(remote_data.get("end_at"))
        if end_at:
            subscription.end_at = end_at
        else:
            current_end = subscription.end_at or datetime.now(timezone.utc)
            subscription.end_at = current_end + timedelta(days=tariff.duration_days)

        subscription.status = SubscriptionStatusEnum.active
        user.balance = user.balance - Decimal(tariff.price)
        await self.session.flush()
        return subscription

    async def delete_remote_user(self, user: User) -> None:
        if not user.remnawave_user_id:
            return
        try:
            await self.remnawave.delete_user(user.remnawave_user_id)
        except RemnawaveAPIError:
            logger.exception("Failed to delete remote user for user_id=%s", user.id)
            await notify_admins(f"⚠️ Ошибка удаления пользователя в Remnawave TG:{user.telegram_id}")
            raise

