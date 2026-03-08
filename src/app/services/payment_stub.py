from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.logs import LogRepository


class PaymentService:
    """
    Stub for payment integrations.
    Replace methods with a real provider SDK (Stripe, YooKassa, etc.).
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.log_repo = LogRepository(session)

    async def create_payment(self, user_id: int, amount: Decimal, provider: str) -> dict:
        await self.log_repo.log_payment(
            user_id=user_id,
            amount=amount,
            provider=provider,
            status="created",
        )
        await self.session.flush()
        return {
            "status": "created",
            "payment_url": "https://example-payments.local/checkout",
        }

    async def process_webhook(self, payload: dict) -> None:
        await self.log_repo.log_payment(
            user_id=payload.get("user_id"),
            amount=Decimal(str(payload.get("amount", "0"))),
            provider=str(payload.get("provider", "unknown")),
            status=str(payload.get("status", "unknown")),
            external_payment_id=payload.get("payment_id"),
            payload=payload,
        )
        await self.session.flush()

