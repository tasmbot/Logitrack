# handlers/order_handler.py
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from core.context import FlowManager
from core.db import get_pool, get_courier_active_deliveries, get_order_details, verify_delivery_ownership, update_order_status, complete_order_transaction
from utils.keyboards import kb_back

logger = logging.getLogger(__name__)

async def show_courier_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not FlowManager.is_courier(context):
        await query.edit_message_text("⚠️ Доступ только для курьеров.", reply_markup=kb_back())
        return

    courier_id = FlowManager.get_courier_id(context)
    pool = get_pool(context)
    if not pool or not courier_id:
        await query.edit_message_text("❌ Ошибка подключения.", reply_markup=kb_back())
        return

    try:
        deliveries = await get_courier_active_deliveries(pool, courier_id)
        if not deliveries:
            await query.edit_message_text("📭 Нет активных заказов.", reply_markup=kb_back())
            return

        keyboard = [[InlineKeyboardButton(f"📦 #{d['order_id']} • {d['status_name']}", callback_data=f"order:select:{d['delivery_id']}")] for d in deliveries]
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="menu:main")])
        await query.edit_message_text(f"📋 Ваши заказы ({len(deliveries)}):", reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.error(f"Ошибка загрузки заказов: {e}")
        await query.edit_message_text("❌ Ошибка загрузки заказов.", reply_markup=kb_back())

async def select_delivery(update: Update, context: ContextTypes.DEFAULT_TYPE, delivery_id: int):
    """Показывает детали заказа и инструкцию по включению геопозиции."""
    query = update.callback_query
    await query.answer()
    if not FlowManager.is_courier(context):
        await query.edit_message_text("⚠️ Доступ запрещён.", reply_markup=kb_back())
        return

    FlowManager.set_delivery(context, delivery_id)
    FlowManager.set_location_shared(context, False)
    FlowManager.set_tracking_active(context, False)

    pool = get_pool(context)
    delivery_info = None
    try:
        delivery_info = get_order_details(pool, delivery_id)
    except Exception as e:
        logger.error(f"Ошибка загрузки деталей: {e}")

    order_id = delivery_info['order_id'] if delivery_info else delivery_id
    info_text = f"✅ *Заказ #{order_id}*\n"
    if delivery_info:
        info_text += (
            f"🏠 Адрес: `{delivery_info['address']}`\n"
            f"💰 Сумма: `{delivery_info['total_price']}`\n"
            f"🏋️ Вес: `{delivery_info['total_weight']}`\n"
            f"📊 Статус: `{delivery_info['status_name']}`\n\n"
        )
    info_text += (
        "📍 *Для начала работы включите трансляцию геопозиции:*\n"
        "1️⃣ Нажмите 📎 в поле ввода\n"
        "2️⃣ Выберите `Геопозиция` → `Транслировать` (1 час)\n\n"
        "⏳ Как только бот получит ваши координаты, появится кнопка старта."
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Назад", callback_data="order:menu")]
    ])
    await query.edit_message_text(info_text, parse_mode="Markdown", reply_markup=keyboard)
    
    
async def start_tracking(update: Update, context: ContextTypes.DEFAULT_TYPE, delivery_id: int):
    query = update.callback_query
    await query.answer()
    if not FlowManager.is_courier(context):
        await query.edit_message_text("⚠️ Доступ запрещён.", reply_markup=kb_back())
        return

    courier_id = FlowManager.get_courier_id(context)
    pool = get_pool(context)
    if not pool:
        await query.edit_message_text("❌ БД недоступна.", reply_markup=kb_back())
        return

    if not await verify_delivery_ownership(pool, delivery_id, courier_id):
        await query.edit_message_text("⚠️ Заказ не закреплён за вами.", reply_markup=kb_back())
        return

    try:
        await update_order_status(pool, delivery_id, 2)  # "В работе"
    except Exception as e:
        logger.error(f"Ошибка смены статуса: {e}")

    FlowManager.set_tracking_active(context, True)
    FlowManager.set_delivery(context, delivery_id)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Завершить заказ", callback_data=f"order:complete:{delivery_id}")],
        [InlineKeyboardButton("⏹ Остановить", callback_data="order:stop")]
    ])
    await query.edit_message_text(
        "📍 *Заказ в пути!*\n🔹 Включите трансляцию геопозиции (📎 → Геопозиция → 1 час)\n🔄 Бот автоматически сохраняет координаты.",
        parse_mode="Markdown", reply_markup=kb
    )

async def complete_order(update: Update, context: ContextTypes.DEFAULT_TYPE, delivery_id: int):
    query = update.callback_query
    await query.answer()
    if not FlowManager.is_courier(context):
        await query.edit_message_text("⚠️ Доступ запрещён.", reply_markup=kb_back())
        return

    pool = get_pool(context)
    courier_id = FlowManager.get_courier_id(context)
    if not pool or not courier_id:
        await query.edit_message_text("❌ Ошибка подключения.", reply_markup=kb_back())
        return

    try:
        result = await complete_order_transaction(pool, delivery_id, courier_id)
        FlowManager.set_tracking_active(context, False)
        FlowManager.reset_delivery_state(context)
        await query.edit_message_text(f"✅ Заказ #{result['order_id']} успешно завершён!")
        await asyncio.sleep(2)
        await show_courier_orders(update, context)
    except ValueError as ve:
        await query.edit_message_text(f"ℹ️ {ve}", reply_markup=kb_back())
    except Exception as e:
        logger.error(f"Ошибка завершения: {e}")
        await query.edit_message_text("❌ Не удалось завершить заказ.", reply_markup=kb_back())

async def stop_tracking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    FlowManager.set_tracking_active(context, False)
    await query.edit_message_text("⏹ Отслеживание остановлено. Координаты не записываются.", reply_markup=kb_back())