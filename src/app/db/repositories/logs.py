from __future__ import annotations

from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AdminActionLog, PaymentLog, ServerSnapshot


class LogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log_admin_action(
        self,
        admin_login: str,
        action: str,
        entity: str,
        entity_id: str | None = None,
        details: dict | None = None,
    ) -> AdminActionLog:
        row = AdminActionLog(
            admin_login=admin_login,
            action=action,
            entity=entity,
            entity_id=entity_id,
            details=details,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def list_admin_actions(self, limit: int = 100) -> list[AdminActionLog]:
        rows = await self.session.scalars(
            select(AdminActionLog).order_by(desc(AdminActionLog.created_at)).limit(limit)
        )
        return list(rows)

    async def log_payment(
        self,
        user_id: int | None,
        amount: Decimal,
        provider: str,
        status: str,
        currency: str = "RUB",
        external_payment_id: str | None = None,
        payload: dict | None = None,
    ) -> PaymentLog:
        row = PaymentLog(
            user_id=user_id,
            amount=amount,
            currency=currency,
            provider=provider,
            status=status,
            external_payment_id=external_payment_id,
            payload=payload,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def add_server_snapshot(
        self,
        server_name: str,
        status: str,
        node_id: str | None = None,
        load_percent: float | None = None,
        users_online: int | None = None,
        raw: dict | None = None,
    ) -> ServerSnapshot:
        row = ServerSnapshot(
            node_id=node_id,
            server_name=server_name,
            status=status,
            load_percent=load_percent,
            users_online=users_online,
            raw=raw,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def list_latest_snapshots(self, limit: int = 200) -> list[ServerSnapshot]:
        rows = await self.session.scalars(
            select(ServerSnapshot).order_by(desc(ServerSnapshot.synced_at)).limit(limit)
        )
        return list(rows)

