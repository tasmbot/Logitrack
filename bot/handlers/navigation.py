# handlers/navigation.py
"""Роутинг команд, кнопок и текстовых сообщений."""
import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from core.context import FlowManager
from core.db import get_pool
from handlers import auth, db_read, db_write
from handlers.order_handler import (
    show_courier_orders,
    select_delivery,
    start_tracking,
    stop_tracking,
    complete_order
)
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
    """Центральный роутер для callback-запросов (кнопок)."""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split(":")
    action = parts[0]
    
    # === Навигация по меню ===
    if query.data == "menu:start":
        await start_cmd(update, context)
        return
    
    elif query.data == "menu:main":
        if FlowManager.is_authenticated(context):
            await query.edit_message_text(
                "📂 *Главное меню*",
                parse_mode="Markdown",
                reply_markup=kb_main_menu()
            )
        else:
            await query.edit_message_text(
                "⚠️ Требуется авторизация.",
                reply_markup=kb_auth_menu()
            )
        return
    
    # === Авторизация ===
    elif action == "auth":
        target = parts[1] if len(parts) > 1 else None
        
        if target == "start":
            FlowManager.set_flow(context, "login_email")
            await query.edit_message_text(
                "🔑 Введите вашу *почту*:",
                parse_mode="Markdown",
                reply_markup=kb_back()
            )
        elif target == "reg":
            FlowManager.set_flow(context, "reg_email")
            await query.edit_message_text(
                "📝 Регистрация. Введите *почту*:",
                parse_mode="Markdown",
                reply_markup=kb_back()
            )
        elif target == "logout":
            FlowManager.logout(context)
            await query.edit_message_text(
                "👋 Вы вышли из системы.",
                reply_markup=kb_auth_menu()
            )
        return
    
    # === Работа с БД ===
    elif action == "db":
        sub_action = parts[1] if len(parts) > 1 else None
        
        if sub_action == "read":
            await query.edit_message_text(
                "📖 Выберите таблицу для чтения:",
                reply_markup=kb_tables("read")
            )
            return
        
        elif sub_action == "write":
            await query.edit_message_text(
                "📝 Выберите таблицу для записи:",
                reply_markup=kb_tables("write")
            )
            return
        
        elif sub_action == "select" and len(parts) >= 4:
            mode = parts[2]
            table = parts[3]
            
            if table not in ALLOWED_TABLES:
                await query.edit_message_text(
                    "⚠️ Таблица недоступна.",
                    reply_markup=kb_back()
                )
                return
            
            schema = TABLE_SCHEMA.get(table)
            if not schema:
                await query.edit_message_text(
                    "⚠️ Таблица не сконфигурирована.",
                    reply_markup=kb_back()
                )
                return
            
            pool = get_pool(context)
            if not pool:
                await query.edit_message_text(
                    "❌ Нет подключения к БД.",
                    reply_markup=kb_back()
                )
                return
            
            if mode == "read":
                await db_read.handle_read_table(query, context, table, schema["read"])
            elif mode == "write":
                await db_write.prepare_write_form(query, context, table, schema["write"])
            return
    
    # === Работа с заказами (только для курьеров) ===
    elif action == "order":
        # Проверка: только курьеры имеют доступ к заказам
        if not FlowManager.is_courier(context):
            await query.edit_message_text(
                "⚠️ Раздел «Мои заказы» доступен только курьерам.",
                reply_markup=kb_back()
            )
            return
        
        sub = parts[1] if len(parts) > 1 else None
        
        # 1. Показать список заказов
        if sub == "menu" or query.data == "menu:orders":
            await show_courier_orders(update, context)
            return
        
        # 2. Выбор конкретного заказа: order:select:123
        elif sub == "select" and len(parts) >= 3:
            try:
                delivery_id = int(parts[2])
                await select_delivery(update, context, delivery_id)
            except (ValueError, IndexError) as e:
                logger.error(f"Ошибка парсинга delivery_id: {e}, parts={parts}")
                await query.edit_message_text(
                    "⚠️ Неверный формат заказа. Попробуйте выбрать снова.",
                    reply_markup=kb_back()
                )
            return
        
        # 3. Начало отслеживания: order:start:123
        elif sub == "start" and len(parts) >= 3:
            try:
                delivery_id = int(parts[2])
                await start_tracking(update, context, delivery_id)
            except (ValueError, IndexError) as e:
                logger.error(f"Ошибка парсинга delivery_id: {e}, parts={parts}")
                await query.edit_message_text(
                    "⚠️ Не удалось начать отслеживание. Попробуйте снова.",
                    reply_markup=kb_back()
                )
            return
        
        # Завершение заказа
        elif sub == "complete" and len(parts) >= 3:
            try:
                delivery_id = int(parts[2])
                await complete_order(update, context, delivery_id)
            except (ValueError, IndexError) as e:
                logger.error(f"Ошибка парсинга delivery_id для завершения: {e}")
                await query.edit_message_text("⚠️ Не удалось завершить заказ.", reply_markup=kb_back())
            return
        
        # 4. Остановка отслеживания
        elif sub == "stop":
            await stop_tracking(update, context)
            return
        
        # 5. Fallback для неизвестных поддействий
        await query.edit_message_text(
            "⚠️ Действие с заказом недоступно.",
            reply_markup=kb_back()
        )
        return
    
    # === Fallback для неизвестных кнопок ===
    await query.edit_message_text(
        "⚠️ Действие недоступно.",
        reply_markup=kb_back()
    )


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
    
    # === Запись в БД: ввод данных ===
    if flow == "write_data":
        return await db_write.handle_write_data(update, context, text)
    
    # === Fallback: эхо-режим ===
    await update.message.reply_text(text)