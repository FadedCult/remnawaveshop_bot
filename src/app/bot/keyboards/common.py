from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import get_settings
from app.db.models import Tariff


def main_menu_keyboard(lang: str, is_admin: bool = False) -> InlineKeyboardMarkup:
    ru = lang == "ru"
    builder = InlineKeyboardBuilder()

    connect_text = "Подключиться" if ru else "Connect"
    builder.row(
        InlineKeyboardButton(
            text=f"🚀 {connect_text}",
            callback_data="menu:connect",
        )
    )
    builder.row(
        InlineKeyboardButton(text="📦 Моя подписка" if ru else "📦 My Subscription", callback_data="menu:subscription"),
        InlineKeyboardButton(text="💳 Баланс" if ru else "💳 Balance", callback_data="menu:balance"),
    )
    builder.row(
        InlineKeyboardButton(text="🛒 Тарифы" if ru else "🛒 Plans", callback_data="menu:tariffs"),
        InlineKeyboardButton(text="📈 Докупить трафик" if ru else "📈 Buy Traffic", callback_data="menu:traffic"),
    )
    builder.row(
        InlineKeyboardButton(text="🛟 Поддержка" if ru else "🛟 Support", callback_data="menu:support"),
        InlineKeyboardButton(text="🌐 RU/EN", callback_data="menu:language"),
    )
    if is_admin:
        builder.row(InlineKeyboardButton(text="⚙️ Админ-панель" if ru else "⚙️ Admin", callback_data="menu:admin"))
    return builder.as_markup()


def tariffs_keyboard(tariffs: list[Tariff], lang: str) -> InlineKeyboardMarkup:
    ru = lang == "ru"
    builder = InlineKeyboardBuilder()
    for tariff in tariffs:
        price = f"{tariff.price} {tariff.currency}"
        builder.row(
            InlineKeyboardButton(
                text=f"{tariff.name} ({price})",
                callback_data=f"buy:{tariff.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="⬅️ Назад" if ru else "⬅️ Back", callback_data="menu:main"))
    return builder.as_markup()


def support_keyboard(lang: str) -> InlineKeyboardMarkup:
    settings = get_settings()
    ru = lang == "ru"
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="Связаться с администратором" if ru else "Contact administrator",
            url=f"https://t.me/{settings.support_username}",
        )
    )
    builder.row(
        InlineKeyboardButton(text="Создать тикет" if ru else "Create ticket", callback_data="support:create"),
        InlineKeyboardButton(text="Мои тикеты" if ru else "My tickets", callback_data="support:my"),
    )
    builder.row(InlineKeyboardButton(text="⬅️ Назад" if ru else "⬅️ Back", callback_data="menu:main"))
    return builder.as_markup()


def subscription_keyboard(lang: str, has_subscription: bool) -> InlineKeyboardMarkup:
    ru = lang == "ru"
    builder = InlineKeyboardBuilder()
    if has_subscription:
        builder.row(
            InlineKeyboardButton(text="🚀 Подключиться" if ru else "🚀 Connect", callback_data="subscription:connect"),
            InlineKeyboardButton(
                text="🔄 Продлить подписку" if ru else "🔄 Extend subscription",
                callback_data="subscription:extend",
            ),
        )
    else:
        builder.row(
            InlineKeyboardButton(text="🛒 Купить подписку" if ru else "🛒 Buy subscription", callback_data="menu:tariffs")
        )
    builder.row(InlineKeyboardButton(text="⬅️ Назад" if ru else "⬅️ Back", callback_data="menu:main"))
    return builder.as_markup()


def admin_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    ru = lang == "ru"
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👥 Пользователи" if ru else "👥 Users", callback_data="admin:users"),
        InlineKeyboardButton(text="🧾 Тикеты" if ru else "🧾 Tickets", callback_data="admin:tickets"),
    )
    builder.row(
        InlineKeyboardButton(text="📣 Рассылки" if ru else "📣 Broadcasts", callback_data="admin:broadcasts"),
        InlineKeyboardButton(text="📊 Опросы" if ru else "📊 Surveys", callback_data="admin:surveys"),
    )
    builder.row(
        InlineKeyboardButton(text="🛒 Тарифы" if ru else "🛒 Plans", callback_data="admin:tariffs"),
        InlineKeyboardButton(text="🖥 Сервера" if ru else "🖥 Servers", callback_data="admin:servers"),
    )
    builder.row(InlineKeyboardButton(text="⬅️ Назад" if ru else "⬅️ Back", callback_data="menu:main"))
    return builder.as_markup()
