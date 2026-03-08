from __future__ import annotations

from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot.i18n import tr
from app.bot.keyboards.common import admin_menu_keyboard
from app.config import get_settings
from app.db.models import BroadcastKindEnum, SegmentEnum
from app.db.repositories.tariffs import TariffRepository
from app.db.repositories.tickets import TicketRepository
from app.db.repositories.users import UserRepository
from app.db.session import SessionLocal
from app.services.broadcast_service import BroadcastService
from app.services.server_service import ServerService
from app.services.survey_service import SurveyService
from app.services.ticket_service import TicketService

router = Router()


async def _is_admin(telegram_id: int) -> bool:
    settings = get_settings()
    if telegram_id in settings.bot_admin_ids:
        return True
    async with SessionLocal() as session:
        user = await UserRepository(session).get_by_telegram_id(telegram_id)
        return bool(user and user.is_admin)


@router.message(Command("admin"))
async def admin_menu(message: Message):
    if not await _is_admin(message.from_user.id):
        await message.answer("Admin only.")
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_by_telegram_id(message.from_user.id)
        lang = user.language.value if user else "ru"
    await message.answer(tr(lang, "admin_menu"), reply_markup=admin_menu_keyboard(lang))


@router.callback_query(F.data == "menu:admin")
async def menu_admin(callback: CallbackQuery):
    if not await _is_admin(callback.from_user.id):
        await callback.answer("Admin only")
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_by_telegram_id(callback.from_user.id)
        lang = user.language.value if user else "ru"
    await callback.message.edit_text(tr(lang, "admin_menu"), reply_markup=admin_menu_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:"))
async def admin_info(callback: CallbackQuery):
    if not await _is_admin(callback.from_user.id):
        await callback.answer("Admin only")
        return
    section = callback.data.split(":")[1]
    hints = {
        "users": "Команды:\n/users_stats\n/user_msg <telegram_id> <text>\n/user_balance <telegram_id> <delta>",
        "tickets": "Команды:\n/tickets_open\n/ticket_reply_admin <ticket_id> <text>\n/ticket_close <ticket_id>",
        "broadcasts": "Команды:\n/broadcast <all|with_subscription|without_subscription> <text>",
        "surveys": "Команды:\n/survey_create <вопрос>\n/survey_close <id>",
        "tariffs": "Команды:\n/tariff_add name|price|days|gb|plan_id|description\n/tariff_delete <id>",
        "servers": "Команды:\n/servers_sync\n/servers_stats",
    }
    await callback.message.answer(hints.get(section, "Раздел"))
    await callback.answer()


@router.message(Command("users_stats"))
async def admin_users_stats(message: Message):
    if not await _is_admin(message.from_user.id):
        return
    async with SessionLocal() as session:
        users = UserRepository(session)
        total = await users.count_all()
        active = await users.count_active_subscribers()
        new_7 = await users.count_new_for_days(7)
    await message.answer(f"Всего: {total}\nАктивные подписки: {active}\nНовые за 7 дней: {new_7}")


@router.message(F.text.startswith("/broadcast "))
async def admin_broadcast(message: Message):
    if not await _is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Формат: /broadcast <all|with_subscription|without_subscription> <text>")
        return
    segment_raw = parts[1]
    text = parts[2]
    try:
        segment = SegmentEnum(segment_raw)
    except ValueError:
        await message.answer("Неверный сегмент.")
        return

    async with SessionLocal() as session:
        service = BroadcastService(session)
        broadcast = await service.create_broadcast(
            title="Рассылка",
            content=text,
            image_url=None,
            target_group=segment,
            kind=BroadcastKindEnum.broadcast,
            created_by=str(message.from_user.id),
        )
        result = await service.send_broadcast(broadcast.id)
        await session.commit()
    await message.answer(f"Отправлено: {result['sent']}, ошибок: {result['failed']}")


@router.message(F.text.startswith("/tariff_add "))
async def admin_tariff_add(message: Message):
    if not await _is_admin(message.from_user.id):
        return
    raw = message.text.replace("/tariff_add ", "", 1)
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) < 6:
        await message.answer("Формат: /tariff_add name|price|days|gb|plan_id|description")
        return
    name, price_raw, days_raw, gb_raw, plan_id, description = parts[:6]
    try:
        price = Decimal(price_raw)
        days = int(days_raw)
        traffic = float(gb_raw) if gb_raw.lower() != "none" else None
    except ValueError:
        await message.answer("Ошибка в числовых полях.")
        return
    async with SessionLocal() as session:
        repo = TariffRepository(session)
        tariff = await repo.create(
            name=name,
            description=description,
            duration_days=days,
            traffic_limit_gb=traffic,
            price=price,
            remnawave_plan_id=plan_id if plan_id.lower() != "none" else None,
        )
        await session.commit()
    await message.answer(f"Тариф создан: #{tariff.id}")


@router.message(F.text.startswith("/tariff_delete "))
async def admin_tariff_delete(message: Message):
    if not await _is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return
    try:
        tariff_id = int(parts[1])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return
    async with SessionLocal() as session:
        repo = TariffRepository(session)
        tariff = await repo.get_by_id(tariff_id)
        if not tariff:
            await message.answer("Тариф не найден.")
            return
        await repo.delete(tariff)
        await session.commit()
    await message.answer("Тариф удален.")


@router.message(F.text.startswith("/tickets_open"))
async def admin_tickets_open(message: Message):
    if not await _is_admin(message.from_user.id):
        return
    async with SessionLocal() as session:
        ticket_repo = TicketRepository(session)
        tickets = await ticket_repo.list_all()
    if not tickets:
        await message.answer("Тикетов нет.")
        return
    lines = []
    for ticket in tickets[:20]:
        lines.append(f"#{ticket.id} [{ticket.status.value}] user={ticket.user.telegram_id} {ticket.subject}")
    await message.answer("\n".join(lines))


@router.message(F.text.startswith("/ticket_reply_admin "))
async def admin_ticket_reply(message: Message):
    if not await _is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Формат: /ticket_reply_admin <ticket_id> <text>")
        return
    try:
        ticket_id = int(parts[1])
    except ValueError:
        await message.answer("ticket_id должен быть числом")
        return
    text = parts[2]
    async with SessionLocal() as session:
        repo = TicketRepository(session)
        ticket = await repo.get_by_id(ticket_id)
        if not ticket:
            await message.answer("Тикет не найден.")
            return
        service = TicketService(session)
        await service.reply_from_admin(ticket, admin_telegram_id=message.from_user.id, text=text)
        await session.commit()
    await message.answer("Ответ отправлен.")


@router.message(F.text.startswith("/ticket_close "))
async def admin_ticket_close(message: Message):
    if not await _is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return
    try:
        ticket_id = int(parts[1])
    except ValueError:
        return
    async with SessionLocal() as session:
        repo = TicketRepository(session)
        ticket = await repo.get_by_id(ticket_id)
        if not ticket:
            await message.answer("Тикет не найден.")
            return
        service = TicketService(session)
        await service.close_ticket(ticket)
        await session.commit()
    await message.answer("Тикет закрыт.")


@router.message(F.text.startswith("/survey_create "))
async def admin_survey_create(message: Message):
    if not await _is_admin(message.from_user.id):
        return
    question = message.text.replace("/survey_create ", "", 1).strip()
    if not question:
        return
    async with SessionLocal() as session:
        service = SurveyService(session)
        survey = await service.create_and_send(question, created_by=str(message.from_user.id))
        await session.commit()
    await message.answer(f"Опрос #{survey.id} создан и отправлен.")


@router.message(F.text.startswith("/survey_close "))
async def admin_survey_close(message: Message):
    if not await _is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return
    try:
        survey_id = int(parts[1])
    except ValueError:
        return
    async with SessionLocal() as session:
        from app.db.repositories.surveys import SurveyRepository

        repo = SurveyRepository(session)
        survey = await repo.get_by_id(survey_id)
        if not survey:
            await message.answer("Опрос не найден.")
            return
        await repo.close(survey)
        await session.commit()
    await message.answer("Опрос закрыт.")


@router.message(F.text.startswith("/servers_sync"))
async def admin_servers_sync(message: Message):
    if not await _is_admin(message.from_user.id):
        return
    async with SessionLocal() as session:
        service = ServerService(session)
        result = await service.sync_servers()
        await session.commit()
    await message.answer(
        f"Синхронизация завершена. servers={len(result['servers'])}, nodes={len(result['nodes'])}"
    )


@router.message(F.text.startswith("/servers_stats"))
async def admin_servers_stats(message: Message):
    if not await _is_admin(message.from_user.id):
        return
    async with SessionLocal() as session:
        service = ServerService(session)
        stats = await service.get_stats()
    await message.answer(f"Статистика Remnawave:\n{stats}")

