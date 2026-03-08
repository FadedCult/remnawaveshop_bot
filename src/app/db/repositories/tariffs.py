from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Tariff


class TariffRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_active(self) -> list[Tariff]:
        rows = await self.session.scalars(select(Tariff).where(Tariff.is_active.is_(True)).order_by(Tariff.price))
        return list(rows)

    async def list_all(self) -> list[Tariff]:
        rows = await self.session.scalars(select(Tariff).order_by(Tariff.created_at.desc()))
        return list(rows)

    async def get_by_id(self, tariff_id: int) -> Tariff | None:
        return await self.session.get(Tariff, tariff_id)

    async def create(
        self,
        name: str,
        description: str | None,
        duration_days: int,
        traffic_limit_gb: float | None,
        price: Decimal,
        currency: str = "RUB",
        remnawave_plan_id: str | None = None,
    ) -> Tariff:
        tariff = Tariff(
            name=name,
            description=description,
            duration_days=duration_days,
            traffic_limit_gb=traffic_limit_gb,
            price=price,
            currency=currency,
            remnawave_plan_id=remnawave_plan_id,
        )
        self.session.add(tariff)
        await self.session.flush()
        return tariff

    async def update(
        self,
        tariff: Tariff,
        *,
        name: str,
        description: str | None,
        duration_days: int,
        traffic_limit_gb: float | None,
        price: Decimal,
        currency: str,
        remnawave_plan_id: str | None,
        is_active: bool,
    ) -> Tariff:
        tariff.name = name
        tariff.description = description
        tariff.duration_days = duration_days
        tariff.traffic_limit_gb = traffic_limit_gb
        tariff.price = price
        tariff.currency = currency
        tariff.remnawave_plan_id = remnawave_plan_id
        tariff.is_active = is_active
        await self.session.flush()
        return tariff

    async def delete(self, tariff: Tariff) -> None:
        await self.session.delete(tariff)
        await self.session.flush()

