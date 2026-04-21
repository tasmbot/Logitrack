# handlers/order_handler.py
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from core.context import FlowManager
from core.db import get_pool, get_courier_active_deliveries, save_delivery_coordinate, update_order_status
from utils.keyboards import kb_back

logger = logging.getLogger(__name__)


async def show_courier_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список активных заказов для авторизованного курьера."""
    query = update.callback_query
    await query.answer()
    
    # Проверка: только для курьеров
    if not FlowManager.is_courier(context):
        await query.edit_message_text(
            "⚠️ Функция доступна только для курьеров.",
            reply_markup=kb_back()
        )
        return
    
    courier_id = FlowManager.get_courier_id(context)
    pool = get_pool(context)
    
    if not pool or not courier_id:
        await query.edit_message_text("❌ Ошибка подключения к БД.", reply_markup=kb_back())
        return

    try:
        deliveries = await get_courier_active_deliveries(pool, courier_id)
        
        if not deliveries:
            await query.edit_message_text(
                "📭 У вас нет активных заказов.\nПроверьте позже или обратитесь к диспетчеру.",
                reply_markup=kb_back()
            )
            return

        # Формируем кнопки с заказами
        keyboard = []
        for d in deliveries:
            btn_text = f"📦 #{d['order_id']} • {d['status_name']}"
            callback_data = f"order:select:{d['delivery_id']}"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=callback_data)])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="menu:main")])
        
        await query.edit_message_text(
            f"📋 Ваши активные заказы ({len(deliveries)}):",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Ошибка загрузки заказов курьера #{courier_id}: {e}")
        await query.edit_message_text(f"❌ Ошибка загрузки заказов: {e}", reply_markup=kb_back())


async def select_delivery(update: Update, context: ContextTypes.DEFAULT_TYPE, delivery_id: int):
    """Показывает детали доставки и кнопку начала отслеживания."""
    query = update.callback_query
    await query.answer()
    
    if not FlowManager.is_courier(context):
        await query.edit_message_text("⚠️ Доступ запрещён.", reply_markup=kb_back())
        return

    # Сохраняем выбранный заказ
    FlowManager.set_selected_delivery(context, delivery_id)
    FlowManager.set_tracking_active(context, False)

    # Получаем детали для отображения
    pool = get_pool(context)
    delivery_info = None
    
    if pool:
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT o.order_id, s.status_name, l.address, 
                    CONCAT('₽ ', o.total_price::numeric) as total_price, CONCAT(COALESCE(o.total_weight, 0), ' кг') as total_weight
                    FROM deliveries d
                    JOIN orders o ON d.order_id = o.order_id
                    JOIN statuses s ON o.status_id = s.status_id
                    JOIN locations l ON d.location_id = l.location_id
                    WHERE d.delivery_id = $1
                """, delivery_id)
                if row:
                    delivery_info = dict(row)
        except Exception as e:
            logger.error(f"Ошибка загрузки деталей доставки: {e}")

    # Формируем текст с информацией
    info_text = f"✅ *Заказ #{delivery_info['order_id'] if delivery_info else delivery_id}*\n"
    if delivery_info:
        info_text += (
            f"📍 Адрес: `{delivery_info['address']}`\n"
            f"💰 Сумма: `{delivery_info['total_price']}`\n"
            f"📊 Статус: `{delivery_info['status_name']}`\n\n"
        )
    info_text += "Нажмите кнопку ниже, чтобы начать отслеживание."

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Начать заказ", callback_data=f"order:start:{delivery_id}")],
        [InlineKeyboardButton("🔙 Назад", callback_data="order:menu")]
    ])
    
    await query.edit_message_text(
        info_text,
        parse_mode="Markdown",
        reply_markup=keyboard
    )

async def select_delivery_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        parts = query.data.split(":")
        if len(parts) != 3 or parts[0] != "order" or parts[1] != "select":
            raise ValueError("Неверный формат callback_data")
        delivery_id = int(parts[2])
        
        
    except (ValueError, IndexError) as e:
        logger.error(f"❌ Ошибка парсинга delivery_id из '{query.data}': {e}")
        await query.edit_message_text("⚠️ Ошибка выбора заказа. Попробуйте снова.")
        return

    FlowManager.set_delivery(context, delivery_id)
    
    # Получаем детали для отображения
    pool = get_pool(context)
    delivery_info = None
    
    if pool:
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT o.order_id, s.status_name, l.address, 
                    CONCAT('₽ ', o.total_price::numeric) as total_price, CONCAT(COALESCE(o.total_weight, 0), ' кг') as total_weight
                    FROM deliveries d
                    JOIN orders o ON d.order_id = o.order_id
                    JOIN statuses s ON o.status_id = s.status_id
                    JOIN locations l ON d.location_id = l.location_id
                    WHERE d.delivery_id = $1
                """, delivery_id)
                if row:
                    delivery_info = dict(row)
        except Exception as e:
            logger.error(f"Ошибка загрузки деталей доставки: {e}")

    # Формируем текст с информацией
    info_text = f"📦 Заказ #{delivery_info['order_id'] if delivery_info else delivery_id}\n"
    if delivery_info:
        info_text += (
            f"🏠 Адрес: {delivery_info['address']}\n"
            f"💰 Сумма: {delivery_info['total_price']}\n"
            f"🏋️‍♂️ Вес: {delivery_info['total_weight']}\n"
            f"📊 Статус: {delivery_info['status_name']}\n\n"
        )
    
    await query.edit_message_text(
        f"{info_text}"
        "📍 Для начала работы включите трансляцию геопозиции:\n"
        "1. Нажмите 📎 (скрепку) в поле ввода\n"
        "2. Выберите «Геопозиция»\n"
        "3. Нажмите «Транслировать на 1 час»\n\n"
        "Как только система получит ваши координаты, появится кнопка старта."
    )

async def start_tracking(update: Update, context: ContextTypes.DEFAULT_TYPE, delivery_id: int):
    """Активирует режим отслеживания, меняет статус на 2 и показывает управление заказом."""
    query = update.callback_query
    await query.answer()
    
    if not FlowManager.is_courier(context):
        await query.edit_message_text("⚠️ Доступ запрещён.", reply_markup=kb_back())
        return

    courier_id = FlowManager.get_courier_id(context)
    pool = get_pool(context)
    
    # Проверка принадлежности заказа
    if pool and courier_id:
        try:
            async with pool.acquire() as conn:
                check = await conn.fetchval(
                    "SELECT 1 FROM deliveries WHERE delivery_id = $1 AND courier_id = $2 LIMIT 1",
                    delivery_id, courier_id
                )
                if not check:
                    await query.edit_message_text("⚠️ Этот заказ не закреплён за вами.", reply_markup=kb_back())
                    return
        except Exception as e:
            logger.error(f"Ошибка проверки доставки: {e}")

    # Обновляем статус заказа на 2 (в работе)
    if pool:
        try:
            await update_order_status(pool, delivery_id, 2)
            logger.info(f"📦 Заказ #{delivery_id}: статус изменён на 2")
        except Exception as e:
            logger.error(f"Ошибка обновления статуса на 2: {e}")

    FlowManager.set_tracking_active(context, True)
    FlowManager.set_selected_delivery(context, delivery_id)

    # Клавиатура с кнопкой завершения
    inline_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Завершить заказ", callback_data=f"order:complete:{delivery_id}")],
        [InlineKeyboardButton("⏹ Остановить отслеживание", callback_data="order:stop")]
    ])
        
    # Инструкция с эмодзи для наглядности
    await query.edit_message_text(
        "📍 *Заказ в пути, режим отслеживания активирован!*\n\n"
        "🔹 *Как включить трансляцию геопозиции:*\n"
        "1️⃣ Нажмите 📎 *(скрепка)* в поле ввода сообщения\n"
        "2️⃣ Выберите `Геопозиция`\n"
        "3️⃣ Нажмите `Транслировать геопозицию`\n"
        "4️⃣ Выберите срок: `1 час` *(рекомендуется)*\n\n"
        "🔄 После включения бот будет *автоматически* сохранять ваши координаты.\n"
        "📱 Трансляция работает в фоне — можно свернуть Telegram.\n\n"
        "⚠️ Если скрепки нет: обновите Telegram или используйте мобильное приложение.\n"
        "✅ Нажмите «Завершить заказ», когда доставите груз.",
        parse_mode="Markdown",
        reply_markup=inline_kb
    )

async def complete_order(update: Update, context: ContextTypes.DEFAULT_TYPE, delivery_id: int):
    """Завершает заказ (статус 3) и возвращает в список заказов."""
    query = update.callback_query
    await query.answer()
    
    if not FlowManager.is_courier(context):
        await query.edit_message_text("⚠️ Доступ запрещён.", reply_markup=kb_back())
        return

    pool = get_pool(context)
    if pool:
        try:
            await update_order_status(pool, delivery_id, 3)
            logger.info(f"✅ Заказ #{delivery_id}: статус изменён на 3 (завершён)")
        except Exception as e:
            logger.error(f"Ошибка обновления статуса на 3: {e}")

    # Сбрасываем состояние отслеживания
    FlowManager.set_tracking_active(context, False)
    FlowManager.set_selected_delivery(context, None)

    # 🔄 Автоматический переход к списку активных заказов
    await show_courier_orders(update, context)

async def stop_tracking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Останавливает отслеживание и очищает состояние."""
    query = update.callback_query
    await query.answer()
    
    FlowManager.set_tracking_active(context, False)
    # Не очищаем selected_delivery, чтобы можно было быстро возобновить
    # Если нужно — раскомментируйте:
    # FlowManager.set_selected_delivery(context, None)
    
    await query.edit_message_text(
        "⏹ Отслеживание остановлено.\n"
        "📍 Координаты больше не записываются.\n"
        "💡 Чтобы продолжить, нажмите «Начать заказ» снова.",
        reply_markup=kb_back()
    )