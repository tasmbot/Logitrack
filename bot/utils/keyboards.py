# utils/keyboards.py
"""Фабрика инлайн-клавиатур для бота."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import ALLOWED_TABLES


def kb_back() -> InlineKeyboardMarkup:
    """Кнопка «Назад» для возврата в главное меню."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Назад", callback_data="menu:main")]
    ])


def kb_auth_menu() -> InlineKeyboardMarkup:
    """Меню авторизации: вход / регистрация."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Войти / Регистрация", callback_data="auth:start")]
    ])


def kb_main_menu() -> InlineKeyboardMarkup:
    """Главное меню — адаптируется под роль пользователя."""
    keyboard = [
        [InlineKeyboardButton("📦 Мои заказы", callback_data="order:menu")],
        [InlineKeyboardButton("🗺 Мой маршрут", callback_data="route:show")],
        [InlineKeyboardButton("🚪 Выйти", callback_data="auth:logout")]
    ]
    return InlineKeyboardMarkup(keyboard)


def kb_tables(action: str) -> InlineKeyboardMarkup:
    """
    Клавиатура со списком таблиц.
    
    Args:
        action: Действие — "read" или "write".
    """
    buttons = [
        [InlineKeyboardButton(table, callback_data=f"db:select:{action}:{table}")]
        for table in ALLOWED_TABLES
    ]
    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)


def kb_auth_fail() -> InlineKeyboardMarkup:
    """Меню при ошибке авторизации."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Повторить вход", callback_data="auth:start")],
        [InlineKeyboardButton("✅ Зарегистрироваться", callback_data="auth:reg")],
        [InlineKeyboardButton("🔙 Назад", callback_data="menu:start")]
    ])