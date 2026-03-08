from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Broadcast, BroadcastKindEnum, SegmentEnum


class BroadcastRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        title: str,
        content: str,
        image_url: str | None,
        target_group: SegmentEnum,
        kind: BroadcastKindEnum,
        periodic_enabled: bool = False,
        periodic_cron: str | None = None,
        created_by: str | None = None,
    ) -> Broadcast:
        broadcast = Broadcast(
            title=title,
            content=content,
            image_url=image_url,
            target_group=target_group,
            kind=kind,
            periodic_enabled=periodic_enabled,
            periodic_cron=periodic_cron,
            created_by=created_by,
        )
        self.session.add(broadcast)
        await self.session.flush()
        return broadcast

    async def list_all(self) -> list[Broadcast]:
        rows = await self.session.scalars(select(Broadcast).order_by(desc(Broadcast.created_at)))
        return list(rows)

    async def list_periodic_enabled(self) -> list[Broadcast]:
        rows = await self.session.scalars(
            select(Broadcast).where(Broadcast.periodic_enabled.is_(True), Broadcast.is_active.is_(True))
        )
        return list(rows)

    async def mark_sent(self, broadcast: Broadcast) -> None:
        broadcast.last_sent_at = datetime.now(timezone.utc)
        await self.session.flush()

    async def disable(self, broadcast: Broadcast) -> None:
        broadcast.is_active = False
        await self.session.flush()

    async def get_by_id(self, broadcast_id: int) -> Broadcast | None:
        return await self.session.get(Broadcast, broadcast_id)

