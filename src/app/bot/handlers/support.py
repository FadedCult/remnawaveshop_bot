from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.i18n import tr
from app.bot.keyboards.common import support_keyboard
from app.bot.states import TicketCreateState
from app.db.repositories.tickets import TicketRepository
from app.db.repositories.users import UserRepository
from app.db.session import SessionLocal
from app.services.ticket_service import TicketService

router = Router()


@router.callback_query(F.data == "support:create")
async def support_create_start(callback: CallbackQuery, state: FSMContext):
    async with SessionLocal() as session:
        user = await UserRepository(session).get_by_telegram_id(callback.from_user.id)
        if not user:
            await callback.answer()
            return
        await state.set_state(TicketCreateState.waiting_subject)
        await callback.message.answer(tr(user.language.value, "enter_subject"))
        await callback.answer()


@router.message(TicketCreateState.waiting_subject)
async def support_subject(message: Message, state: FSMContext):
    await state.update_data(subject=message.text.strip())
    await state.set_state(TicketCreateState.waiting_message)
    async with SessionLocal() as session:
        user = await UserRepository(session).get_by_telegram_id(message.from_user.id)
        lang = user.language.value if user else "ru"
    await message.answer(tr(lang, "enter_ticket_text"))


@router.message(TicketCreateState.waiting_message)
async def support_message(message: Message, state: FSMContext):
    data = await state.get_data()
    subject = data.get("subject", "Без темы")
    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(message.from_user.id)
        if not user:
            await state.clear()
            return
        service = TicketService(session)
        ticket = await service.create_ticket(user, subject=subject, text=message.text.strip())
        await session.commit()
        await message.answer(
            tr(user.language.value, "ticket_created", ticket_id=ticket.id),
            reply_markup=support_keyboard(user.language.value),
        )
    await state.clear()


@router.callback_query(F.data == "support:my")
async def support_my_tickets(callback: CallbackQuery):
    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        ticket_repo = TicketRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        if not user:
            await callback.answer()
            return
        tickets = await ticket_repo.list_user_tickets(user.id)
        if not tickets:
            await callback.message.answer(
                tr(user.language.value, "tickets_empty"), reply_markup=support_keyboard(user.language.value)
            )
            await callback.answer()
            return
        lines = []
        for t in tickets[:10]:
            last = t.messages[-1].text[:80] if t.messages else "-"
            lines.append(f"#{t.id} [{t.status.value}] {t.subject}\n↳ {last}")
        lines.append("\nЧтобы ответить: /ticket_reply <id> <текст>")
        await callback.message.answer("\n\n".join(lines), reply_markup=support_keyboard(user.language.value))
        await callback.answer()


@router.message(F.text.startswith("/ticket_reply"))
async def support_reply_existing(message: Message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Формат: /ticket_reply <id> <текст>")
        return
    try:
        ticket_id = int(parts[1])
    except ValueError:
        await message.answer("ID тикета должен быть числом.")
        return
    reply_text = parts[2].strip()
    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        ticket_repo = TicketRepository(session)
        user = await user_repo.get_by_telegram_id(message.from_user.id)
        if not user:
            return
        ticket = await ticket_repo.get_by_id(ticket_id)
        if not ticket or ticket.user_id != user.id:
            await message.answer("Тикет не найден.")
            return
        service = TicketService(session)
        await service.reply_from_user(ticket, user, reply_text)
        await session.commit()
        await message.answer(tr(user.language.value, "ticket_reply_saved"))

