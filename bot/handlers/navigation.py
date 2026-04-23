# handlers/navigation.py
"""Роутинг команд, кнопок и текстовых сообщений."""
import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from core.context import FlowManager
from core.db import get_pool
from handlers import auth
from handlers.order_handler import (
    show_courier_orders,
    select_delivery,
    start_tracking,
    stop_tracking,
    complete_order
)
from handlers.tracking_handler import start_tracking_callback
from utils.keyboards import (
    kb_back, kb_auth_menu, kb_main_menu, kb_tables, kb_auth_fail
)
from config import ALLOWED_TABLES, TABLE_SCHEMA

logger = logging.getLogger(__name__)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    FlowManager.reset(context)
    
    text = (
        "🤖 *Привет! Я универсальный Telegram-бот.*\n\n"
        "🔹 `Эхо-режим`: повторяю ваши сообщения\n"
        "🔹 `БД`: читаю и записываю данные в PostgreSQL\n"
        "🔹 `Навигация`: всё управление через кнопки\n\n"
        "Для доступа к функциям БД необходимо авторизоваться."
    )
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=kb_auth_menu()
    )


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /cancel — сброс состояния."""
    FlowManager.reset(context)
    await update.message.reply_text(
        "🔄 Состояние сброшено. Начните с /start",
        reply_markup=kb_auth_menu()
    )


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Диспетчер callback-запросов: маршрутизирует по префиксу, убирает вложенные if/elif."""
    query = update.callback_query
    await query.answer()
    data = query.data

    # Прямые соответствия меню
    if data == "menu:start":
        return await start_cmd(update, context)
    if data == "menu:main":
        if FlowManager.is_authenticated(context):
            await query.edit_message_text("📂 *Главное меню*", parse_mode="Markdown", reply_markup=kb_main_menu())
        else:
            await query.edit_message_text("⚠️ Требуется авторизация.", reply_markup=kb_auth_menu())
        return

    # Делегирование по модулям
    if data.startswith("auth:"):
        return await _route_auth(update, context, data)
    if data.startswith("db:"):
        return await _route_db(update, context, data)
    if data.startswith("order:"):
        return await _route_order(update, context, data)

    # Fallback
    await query.edit_message_text("⚠️ Действие недоступно.", reply_markup=kb_back())


async def _route_auth(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    _, action = data.split(":", 1)
    query = update.callback_query
    
    if action == "start":
        FlowManager.set_flow(context, "login_email")
        await query.edit_message_text("🔑 Введите вашу *почту*:", parse_mode="Markdown", reply_markup=kb_back())
    elif action == "reg":
        FlowManager.set_flow(context, "reg_email")
        await query.edit_message_text("📝 Регистрация. Введите *почту*:", parse_mode="Markdown", reply_markup=kb_back())
    elif action == "logout":
        FlowManager.logout(context)
        await query.edit_message_text("👋 Вы вышли из системы.", reply_markup=kb_auth_menu())
    else:
        await query.edit_message_text("⚠️ Неизвестное действие авторизации.", reply_markup=kb_back())


async def _route_db(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    parts = data.split(":")
    query = update.callback_query
    if len(parts) < 2: 
        return await query.edit_message_text("⚠️ Неверный формат.", reply_markup=kb_back())

    sub = parts[1]
    if sub == "read":
        await query.edit_message_text("📖 Выберите таблицу для чтения:", reply_markup=kb_tables("read"))
    elif sub == "write":
        await query.edit_message_text("📝 Выберите таблицу для записи:", reply_markup=kb_tables("write"))
    elif sub == "select" and len(parts) >= 4:
        mode, table = parts[2], parts[3]
        if table not in ALLOWED_TABLES:
            return await query.edit_message_text("⚠️ Таблица недоступна.", reply_markup=kb_back())
        schema = TABLE_SCHEMA.get(table)
        if not schema:
            return await query.edit_message_text("⚠️ Таблица не сконфигурирована.", reply_markup=kb_back())
        pool = get_pool(context)
        if not pool:
            return await query.edit_message_text("❌ Нет подключения к БД.", reply_markup=kb_back())
            
    else:
        await query.edit_message_text("⚠️ Действие с БД недоступно.", reply_markup=kb_back())


async def _route_order(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    if not FlowManager.is_courier(context):
        return await update.callback_query.edit_message_text("⚠️ Раздел доступен только курьерам.", reply_markup=kb_back())

    parts = data.split(":")
    sub = parts[1] if len(parts) > 1 else None
    query = update.callback_query

    if sub == "menu":
        return await show_courier_orders(update, context)
    if sub == "select" and len(parts) >= 3:
        try:
            return await select_delivery(update, context, int(parts[2]))
        except ValueError:
            return await query.edit_message_text("⚠️ Неверный ID заказа.", reply_markup=kb_back())
    if sub == "start" and len(parts) >= 3:
        try:
            return await start_tracking_callback(update, context)
        except ValueError:
            return await query.edit_message_text("⚠️ Ошибка старта.", reply_markup=kb_back())
    if sub == "complete" and len(parts) >= 3:
        try:
            return await complete_order(update, context, int(parts[2]))
        except ValueError:
            return await query.edit_message_text("⚠️ Ошибка завершения.", reply_markup=kb_back())
    if sub == "stop":
        return await stop_tracking(update, context)

    await query.edit_message_text("⚠️ Действие с заказом недоступно.", reply_markup=kb_back())
    

async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Центральный роутер для текстовых сообщений (конечный автомат)."""
    if not update.message or not update.message.text:
        return
    
    text = update.message.text.strip()
    flow = FlowManager.get_flow(context)
    
    # === Авторизация: ввод email ===
    if flow == "login_email":
        return await auth.handle_login_email(update, context, text)
    
    # === Авторизация: ввод пароля ===
    if flow == "login_pass":
        return await auth.handle_login_pass(update, context, text)
    
    # === Регистрация: пошаговый сбор данных ===
    if flow == "reg_email":
        return await auth.handle_reg_email(update, context, text)
    
    if flow == "reg_fullname":
        return await auth.handle_reg_fullname(update, context, text)
    
    if flow == "reg_phone":
        return await auth.handle_reg_phone(update, context, text)
    
    if flow == "reg_pass":
        return await auth.handle_reg_pass(update, context, text)
    
    # === Fallback: эхо-режим ===
    await update.message.reply_text(text)