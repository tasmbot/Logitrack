# handlers/tracking_handler.py
"""
Обработчики управления трекингом заказа:
• start_tracking_callback: Активирует запись координат после получения первой геопозиции
• complete_order_callback: Атомарно завершает заказ и фиксирует время доставки
• stop_tracking_callback: Временно приостанавливает отправку координат
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from core.context import FlowManager
from core.db import get_pool, update_order_status
from utils.keyboards import kb_back

logger = logging.getLogger(__name__)


async def start_tracking_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Активирует режим отслеживания после получения первой геопозиции."""
    query = update.callback_query
    await query.answer()

    # 🔒 Проверяем, что курьер уже начал трансляцию
    if not FlowManager.is_location_shared(context):
        await query.edit_message_text("⚠️ Сначала включите трансляцию геопозиции!")
        return

    delivery_id = FlowManager.get_delivery(context)
    if not delivery_id:
        await query.edit_message_text("⚠️ Сначала выберите заказ!")
        return

    pool = get_pool(context)
    if pool:
        try:
            # 📦 Меняем статус заказа на 2 ("В пути")
            await update_order_status(pool, delivery_id, 2)
            logger.info(f"📦 Заказ #{delivery_id}: статус изменён на 2")
        except Exception as e:
            logger.error(f"Ошибка смены статуса на 2: {e}")

    # 🔥 Включаем флаг активной отправки в Kafka
    FlowManager.set_tracking_active(context, True)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Завершить заказ", callback_data=f"order:complete:{delivery_id}")],
        [InlineKeyboardButton("⏹ Остановить", callback_data=f"order:stop:{delivery_id}")]
    ])
    await query.edit_message_text(
        "📡 *Отслеживание активировано!*\n"
        "📍 Координаты автоматически передаются в систему.\n"
        "Не выключайте трансляцию до завершения доставки.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


async def complete_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Атомарно завершает заказ, фиксирует время и возвращает в меню."""
    query = update.callback_query
    await query.answer()

    try:
        delivery_id = int(query.data.split(":")[-1])
    except (ValueError, IndexError):
        await query.edit_message_text("⚠️ Ошибка формата запроса.")
        return

    pool = get_pool(context)
    courier_id = FlowManager.get_courier_id(context)
    if not pool or not courier_id:
        await query.edit_message_text("❌ Ошибка подключения или сессии.")
        return

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                # 1. Проверка доставки, владения и статуса
                delivery = await conn.fetchrow("""
                    SELECT d.courier_id, d.actual_delivery_datetime, o.order_id
                    FROM deliveries d
                    JOIN orders o ON d.order_id = o.order_id
                    WHERE d.delivery_id = $1
                """, delivery_id)

                if not delivery:
                    await query.edit_message_text("⚠️ Доставка не найдена в системе.")
                    return
                if delivery["actual_delivery_datetime"]:
                    await query.edit_message_text("ℹ️ Этот заказ уже был завершён ранее.")
                    return
                if delivery["courier_id"] != courier_id:
                    await query.edit_message_text("⚠️ Этот заказ не закреплён за вами.")
                    return

                # 2. Фиксация времени доставки
                await conn.execute("""
                    UPDATE deliveries 
                    SET actual_delivery_datetime = CURRENT_TIMESTAMP 
                    WHERE delivery_id = $1
                """, delivery_id)

                # 3. Смена статуса заказа на "delivered"
                status_id = await conn.fetchval("""
                    SELECT status_id FROM statuses WHERE status_name = 'delivered' LIMIT 1
                """)
                if status_id:
                    await conn.execute("""
                        UPDATE orders SET status_id = $1 WHERE order_id = $2
                    """, status_id, delivery["order_id"])

        # 4. Полный сброс состояния доставки
        FlowManager.set_tracking_active(context, False)
        FlowManager.set_location_shared(context, False)
        FlowManager.set_delivery(context, None)

        await query.edit_message_text(
            f"✅ Заказ #{delivery['order_id']} успешно завершён!\n"
            f"📅 Время доставки зафиксировано в системе.\n"
            f"📦 Перейдите в меню, чтобы взять новый заказ.",
            reply_markup=kb_back()
        )
    except Exception as e:
        logger.error(f"❌ Ошибка завершения заказа #{delivery_id}: {e}")
        await query.edit_message_text("❌ Не удалось завершить заказ. Проверьте связь.")


async def stop_tracking_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приостанавливает отправку координат, сохраняя возможность быстрого возобновления."""
    query = update.callback_query
    await query.answer()

    try:
        delivery_id = int(query.data.replace("order:stop:", ""))
    except ValueError:
        await query.edit_message_text("⚠️ Ошибка парсинга ID.")
        return

    # Выключаем только отправку в Kafka, но оставляем location_shared=True
    FlowManager.set_tracking_active(context, False)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Возобновить отслеживание", callback_data="start_tracking")]
    ])
    await query.edit_message_text(
        f"⏹ Отслеживание заказа #{delivery_id} остановлено.\n"
        f"📍 Координаты больше не передаются.\n"
        f"Нажмите «Возобновить», чтобы продолжить.",
        reply_markup=keyboard
    )