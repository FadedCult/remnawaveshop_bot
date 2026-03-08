from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Ticket, TicketMessage, TicketSenderRoleEnum, TicketStatusEnum


class TicketRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_ticket(self, user_id: int, subject: str, first_message_text: str) -> Ticket:
        ticket = Ticket(user_id=user_id, subject=subject)
        self.session.add(ticket)
        await self.session.flush()
        message = TicketMessage(
            ticket_id=ticket.id,
            sender_role=TicketSenderRoleEnum.user,
            text=first_message_text,
        )
        self.session.add(message)
        await self.session.flush()
        return ticket

    async def get_by_id(self, ticket_id: int) -> Ticket | None:
        query = (
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(selectinload(Ticket.messages), selectinload(Ticket.user))
        )
        return await self.session.scalar(query)

    async def list_user_tickets(self, user_id: int) -> list[Ticket]:
        rows = await self.session.scalars(
            select(Ticket)
            .where(Ticket.user_id == user_id)
            .order_by(desc(Ticket.updated_at))
            .options(selectinload(Ticket.messages))
        )
        return list(rows)

    async def list_all(self, status: TicketStatusEnum | None = None) -> list[Ticket]:
        query = (
            select(Ticket)
            .order_by(desc(Ticket.updated_at))
            .options(selectinload(Ticket.messages), selectinload(Ticket.user))
        )
        if status:
            query = query.where(Ticket.status == status)
        rows = await self.session.scalars(query)
        return list(rows)

    async def add_message(
        self,
        ticket: Ticket,
        sender_role: TicketSenderRoleEnum,
        text: str,
        sender_telegram_id: int | None = None,
    ) -> TicketMessage:
        message = TicketMessage(
            ticket_id=ticket.id,
            sender_role=sender_role,
            sender_telegram_id=sender_telegram_id,
            text=text,
        )
        self.session.add(message)
        if sender_role == TicketSenderRoleEnum.admin:
            ticket.status = TicketStatusEnum.in_progress
        else:
            ticket.status = TicketStatusEnum.open
        await self.session.flush()
        return message

    async def set_status(self, ticket: Ticket, status: TicketStatusEnum) -> Ticket:
        ticket.status = status
        await self.session.flush()
        return ticket

