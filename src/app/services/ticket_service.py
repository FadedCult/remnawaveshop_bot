from __future__ import annotations

import logging

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Ticket, TicketSenderRoleEnum, TicketStatusEnum, User
from app.db.repositories.tickets import TicketRepository

logger = logging.getLogger(__name__)


class TicketService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = TicketRepository(session)
        self.settings = get_settings()

    async def create_ticket(self, user: User, subject: str, text: str) -> Ticket:
        ticket = await self.repo.create_ticket(user.id, subject, text)
        await self.session.flush()
        await self._notify_admins_new_ticket(ticket.id, user.telegram_id, subject, text)
        return ticket

    async def reply_from_user(self, ticket: Ticket, user: User, text: str) -> None:
        await self.repo.add_message(ticket, TicketSenderRoleEnum.user, text, sender_telegram_id=user.telegram_id)
        await self.session.flush()
        await self._notify_admins_user_reply(ticket.id, user.telegram_id, text)

    async def reply_from_admin(self, ticket: Ticket, admin_telegram_id: int, text: str) -> None:
        await self.repo.add_message(ticket, TicketSenderRoleEnum.admin, text, sender_telegram_id=admin_telegram_id)
        await self.session.flush()
        if ticket.user:
            await self._send_to_user(ticket.user.telegram_id, f"Ответ поддержки по тикету #{ticket.id}:\n\n{text}")

    async def close_ticket(self, ticket: Ticket) -> None:
        await self.repo.set_status(ticket, TicketStatusEnum.closed)
        await self.session.flush()
        if ticket.user:
            await self._send_to_user(
                ticket.user.telegram_id,
                f"Тикет #{ticket.id} закрыт. Если проблема осталась, создайте новый тикет.",
            )

    async def _notify_admins_new_ticket(self, ticket_id: int, telegram_id: int, subject: str, text: str) -> None:
        if not self.settings.bot_admin_ids or not self.settings.bot_token:
            return
        message = (
            f"🆕 Новый тикет #{ticket_id}\n"
            f"Пользователь: `{telegram_id}`\n"
            f"Тема: {subject}\n\n"
            f"{text}"
        )
        await self._send_to_admins(message)

    async def _notify_admins_user_reply(self, ticket_id: int, telegram_id: int, text: str) -> None:
        if not self.settings.bot_admin_ids or not self.settings.bot_token:
            return
        message = (
            f"💬 Ответ пользователя в тикете #{ticket_id}\n"
            f"Пользователь: `{telegram_id}`\n\n"
            f"{text}"
        )
        await self._send_to_admins(message)

    async def _send_to_admins(self, text: str) -> None:
        bot = Bot(self.settings.bot_token)
        try:
            for admin_id in self.settings.bot_admin_ids:
                try:
                    await bot.send_message(admin_id, text)
                except Exception:
                    logger.exception("Failed to send ticket notification to admin_id=%s", admin_id)
        finally:
            await bot.session.close()

    async def _send_to_user(self, telegram_id: int, text: str) -> None:
        if not self.settings.bot_token:
            return
        bot = Bot(self.settings.bot_token)
        try:
            await bot.send_message(telegram_id, text)
        finally:
            await bot.session.close()
