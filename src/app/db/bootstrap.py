from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import select

from app.db.base import Base
from app.db.models import Tariff
from app.db.session import SessionLocal, engine

logger = logging.getLogger(__name__)


async def init_db(with_seed: bool = True) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    if with_seed:
        await seed_defaults()
    logger.info("Database initialized")


async def seed_defaults() -> None:
    async with SessionLocal() as session:
        exists = await session.scalar(select(Tariff).limit(1))
        if exists:
            return
        session.add_all(
            [
                Tariff(
                    name="Starter 30d",
                    description="Базовый тариф на 30 дней",
                    duration_days=30,
                    traffic_limit_gb=100,
                    price=Decimal("299.00"),
                    currency="RUB",
                ),
                Tariff(
                    name="Pro 90d",
                    description="Продвинутый тариф на 90 дней",
                    duration_days=90,
                    traffic_limit_gb=500,
                    price=Decimal("799.00"),
                    currency="RUB",
                ),
            ]
        )
        await session.commit()

