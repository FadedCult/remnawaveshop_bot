from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.i18n import tr
from app.bot.keyboards.common import main_menu_keyboard, subscription_keyboard, support_keyboard, tariffs_keyboard
from app.config import get_settings
from app.db.repositories.subscriptions import SubscriptionRepository
from app.db.repositories.tariffs import TariffRepository
from app.db.repositories.users import UserRepository
from app.db.session import SessionLocal
from app.exceptions import BusinessLogicError
from app.services.subscription_service import SubscriptionService

router = Router()


async def _ensure_user(session: AsyncSession, message: Message):
    settings = get_settings()
    user_repo = UserRepository(session)
    return await user_repo.upsert_telegram_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        is_admin=message.from_user.id in settings.bot_admin_ids,
    )


async def _format_subscription_text(session: AsyncSession, user_id: int, lang: str) -> str:
    sub_repo = SubscriptionRepository(session)
    tariff_repo = TariffRepository(session)
    subscription = await sub_repo.get_active_for_user(user_id)
    if not subscription:
        return tr(lang, "no_subscription")
    tariff_name = "-"
    if subscription.tariff_id:
        tariff = await tariff_repo.get_by_id(subscription.tariff_id)
        tariff_name = tariff.name if tariff else "-"
    end_at = subscription.end_at.strftime("%Y-%m-%d") if subscription.end_at else "-"
    return f"{tariff_name} (до {end_at})"


@router.message(CommandStart())
async def start_cmd(message: Message):
    async with SessionLocal() as session:
        user = await _ensure_user(session, message)
        subscription_text = await _format_subscription_text(session, user.id, user.language.value)
        text = (
            f"{tr(user.language.value, 'welcome')}\n\n"
            f"{tr(user.language.value, 'main_info', name=user.full_name or user.username or user.telegram_id, subscription=subscription_text)}"
        )
        await session.commit()
    await message.answer(text, reply_markup=main_menu_keyboard(user.language.value, is_admin=user.is_admin))


@router.callback_query(F.data == "menu:main")
async def menu_main(callback: CallbackQuery):
    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        if not user:
            await callback.message.answer("/start")
            await callback.answer()
            return
        subscription_text = await _format_subscription_text(session, user.id, user.language.value)
        text = tr(
            user.language.value,
            "main_info",
            name=user.full_name or user.username or user.telegram_id,
            subscription=subscription_text,
        )
        await callback.message.edit_text(text, reply_markup=main_menu_keyboard(user.language.value, user.is_admin))
        await callback.answer()


@router.callback_query(F.data == "menu:balance")
async def menu_balance(callback: CallbackQuery):
    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        if not user:
            await callback.answer()
            return
        text = tr(user.language.value, "balance", balance=user.balance)
        await callback.message.edit_text(text, reply_markup=main_menu_keyboard(user.language.value, user.is_admin))
        await callback.answer()


@router.callback_query(F.data == "menu:connect")
async def menu_connect(callback: CallbackQuery):
    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        sub_repo = SubscriptionRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        if not user:
            await callback.answer()
            return
        subscription = await sub_repo.get_active_for_user(user.id)
        if not subscription or not subscription.connect_url:
            await callback.message.edit_text(
                tr(user.language.value, "subscription_none"),
                reply_markup=main_menu_keyboard(user.language.value, user.is_admin),
            )
            await callback.answer()
            return
        text = "Нажмите кнопку ниже для подключения." if user.language.value == "ru" else "Use button below to connect."
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🚀 Open MiniApp", web_app=WebAppInfo(url=subscription.connect_url))],
                [InlineKeyboardButton(text="⬅️ Back", callback_data="menu:main")],
            ]
        )
        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()


@router.callback_query(F.data == "menu:traffic")
async def menu_traffic(callback: CallbackQuery):
    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        if not user:
            await callback.answer()
            return
        text = "Функция докупки трафика может быть подключена через Remnawave add-ons API."
        if user.language.value == "en":
            text = "Traffic top-up can be enabled through Remnawave add-ons API."
        await callback.message.edit_text(text, reply_markup=main_menu_keyboard(user.language.value, user.is_admin))
        await callback.answer()


@router.callback_query(F.data == "menu:language")
async def menu_language(callback: CallbackQuery):
    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        if not user:
            await callback.answer()
            return
        new_lang = "en" if user.language.value == "ru" else "ru"
        await user_repo.set_language(user, new_lang)
        await session.commit()
        await callback.message.edit_text(
            tr(new_lang, "language_changed"),
            reply_markup=main_menu_keyboard(new_lang, user.is_admin),
        )
        await callback.answer()


@router.callback_query(F.data == "menu:tariffs")
async def menu_tariffs(callback: CallbackQuery):
    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        tariff_repo = TariffRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        if not user:
            await callback.answer()
            return
        tariffs = await tariff_repo.list_active()
        if not tariffs:
            text = "Нет доступных тарифов." if user.language.value == "ru" else "No plans available."
        else:
            lines = [tr(user.language.value, "tariffs_title"), ""]
            for t in tariffs:
                lines.append(
                    f"#{t.id} {t.name} | {t.duration_days}d | {t.traffic_limit_gb or '∞'} GB | {t.price} {t.currency}"
                )
            text = "\n".join(lines)
        await callback.message.edit_text(text, reply_markup=tariffs_keyboard(tariffs, user.language.value))
        await callback.answer()


@router.callback_query(F.data.startswith("buy:"))
async def buy_tariff(callback: CallbackQuery):
    tariff_id = int(callback.data.split(":")[1])
    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        tariff_repo = TariffRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        tariff = await tariff_repo.get_by_id(tariff_id)
        if not user or not tariff:
            await callback.answer("Not found")
            return
        service = SubscriptionService(session)
        try:
            await service.buy_subscription(user, tariff)
            await session.commit()
            text = tr(user.language.value, "buy_success")
        except BusinessLogicError:
            await session.rollback()
            text = tr(user.language.value, "insufficient_balance")
        except Exception:
            await session.rollback()
            text = "Ошибка оформления подписки." if user.language.value == "ru" else "Subscription failed."
        await callback.message.edit_text(text, reply_markup=main_menu_keyboard(user.language.value, user.is_admin))
        await callback.answer()


@router.callback_query(F.data == "menu:subscription")
async def menu_subscription(callback: CallbackQuery):
    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        sub_repo = SubscriptionRepository(session)
        tariff_repo = TariffRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        if not user:
            await callback.answer()
            return
        subscription = await sub_repo.get_active_for_user(user.id)
        if not subscription:
            text = tr(user.language.value, "subscription_none")
            await callback.message.edit_text(
                text,
                reply_markup=subscription_keyboard(user.language.value, has_subscription=False),
            )
            await callback.answer()
            return
        tariff_name = "-"
        if subscription.tariff_id:
            tariff = await tariff_repo.get_by_id(subscription.tariff_id)
            if tariff:
                tariff_name = tariff.name
        end_at = subscription.end_at.strftime("%Y-%m-%d") if subscription.end_at else "-"
        text = f"{tariff_name}\nEnd: {end_at}"
        await callback.message.edit_text(
            text,
            reply_markup=subscription_keyboard(user.language.value, has_subscription=True),
        )
        await callback.answer()


@router.callback_query(F.data == "subscription:connect")
async def subscription_connect(callback: CallbackQuery):
    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        sub_repo = SubscriptionRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        if not user:
            await callback.answer()
            return
        subscription = await sub_repo.get_active_for_user(user.id)
        if not subscription:
            await callback.message.edit_text(
                tr(user.language.value, "subscription_none"),
                reply_markup=main_menu_keyboard(user.language.value, user.is_admin),
            )
            await callback.answer()
            return
        if subscription.connect_url:
            await callback.message.answer(subscription.connect_url)
        else:
            await callback.message.answer(tr(user.language.value, "connect_missing"))
        await callback.answer()


@router.callback_query(F.data == "subscription:extend")
async def subscription_extend(callback: CallbackQuery):
    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        sub_repo = SubscriptionRepository(session)
        tariff_repo = TariffRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        if not user:
            await callback.answer()
            return
        subscription = await sub_repo.get_active_for_user(user.id)
        if not subscription or not subscription.tariff_id:
            await callback.message.answer(tr(user.language.value, "subscription_none"))
            await callback.answer()
            return
        tariff = await tariff_repo.get_by_id(subscription.tariff_id)
        if not tariff:
            await callback.answer()
            return
        service = SubscriptionService(session)
        try:
            await service.extend_subscription(user, subscription, tariff)
            await session.commit()
            await callback.message.answer(tr(user.language.value, "buy_success"))
        except BusinessLogicError:
            await session.rollback()
            await callback.message.answer(tr(user.language.value, "insufficient_balance"))
        except Exception:
            await session.rollback()
            await callback.message.answer("Ошибка продления подписки.")
        await callback.answer()


@router.callback_query(F.data == "menu:support")
async def menu_support(callback: CallbackQuery):
    async with SessionLocal() as session:
        user = await UserRepository(session).get_by_telegram_id(callback.from_user.id)
        if not user:
            await callback.answer()
            return
        await callback.message.edit_text(
            tr(user.language.value, "support_menu"),
            reply_markup=support_keyboard(user.language.value),
        )
        await callback.answer()
