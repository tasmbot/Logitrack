# handlers/tracking_handler.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import logging

from core.context import FlowManager

logger = logging.getLogger(__name__)

async def start_tracking_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not FlowManager.is_location_shared(context):
        await query.edit_message_text("⚠️ Сначала включите трансляцию геопозиции!")
        return

    delivery_id = FlowManager.get_delivery(context)
    if not delivery_id:
        await query.edit_message_text("⚠️ Сначала выберите заказ!")
        return

    # 🔥 Включаем режим отправки координат в Kafka
    FlowManager.set_tracking_active(context, True)

    # 🔹 Добавляем кнопки управления
    keyboard = [
        [
            InlineKeyboardButton("✅ Завершить заказ", callback_data=f"order:complete:{delivery_id}"),
            InlineKeyboardButton("⏹ Остановить", callback_data=f"order:stop:{delivery_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"📡 Отслеживание заказа #{delivery_id} началось!\n"
        f"📍 Ваши координаты теперь автоматически передаются в систему.\n"
        f"Не выключайте трансляцию геопозиции до завершения доставки.",
        reply_markup=reply_markup
    )
    
# === Завершение заказа ===
async def complete_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # 🔹 Безопасный парсинг delivery_id
    try:
        delivery_id = int(query.data.split(":")[-1])
    except (ValueError, IndexError):
        await query.edit_message_text("⚠️ Ошибка формата запроса. Попробуйте снова.")
        return

    pool = context.bot_data.get("db_pool")
    courier_id = FlowManager.get_courier_id(context)

    if not pool:
        await query.edit_message_text("❌ Ошибка подключения к БД.")
        return
    if not courier_id:
        await query.edit_message_text("⚠️ Сессия курьера не найдена. Перезайдите в бот.")
        return

    try:
        async with pool.acquire() as conn:
            # 🟢 Атомарная транзакция: всё или ничего
            async with conn.transaction():
                # 1. Проверка существования, владения и статуса
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

                # 2. Фиксация времени доставки (используем серверное время БД)
                await conn.execute("""
                    UPDATE deliveries
                    SET actual_delivery_datetime = CURRENT_TIMESTAMP
                    WHERE delivery_id = $1
                """, delivery_id)

                # 3. Обновление статуса заказа на "Доставлен"
                status_id = await conn.fetchval("""
                    SELECT status_id FROM statuses WHERE status_name = 'delivered' LIMIT 1
                """)
                if status_id:
                    await conn.execute("""
                        UPDATE orders SET status_id = $1 WHERE order_id = $2
                    """, status_id, delivery["order_id"])

        # 4. Сброс локального состояния курьера
        FlowManager.set_tracking_active(context, False)
        FlowManager.set_location_shared(context, False)
        FlowManager.set_delivery(context, None)

        # 5. Подтверждение
        await query.edit_message_text(
            f"✅ Заказ #{delivery['order_id']} успешно завершён!\n"
            f"📅 Время доставки зафиксировано в системе.\n"
            f"📦 Перейдите в меню, чтобы взять новый заказ."
        )

    except Exception as e:
        logger.error(f"❌ Ошибка завершения заказа #{delivery_id}: {e}")
        await query.edit_message_text("❌ Не удалось завершить заказ. Проверьте связь или обратитесь к диспетчеру.")

# === Остановка отслеживания (без завершения заказа) ===
async def stop_tracking_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    delivery_id = int(query.data.replace("order:stop:", ""))
    
    # Только выключаем режим отправки в Kafka, статус заказа не меняем
    FlowManager.set_tracking_active(context, False)
    # location_shared оставляем True, чтобы можно было быстро возобновить

    # Возвращаем кнопки старта
    keyboard = [[InlineKeyboardButton("🚀 Возобновить отслеживание", callback_data="start_tracking")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"⏹ Отслеживание заказа #{delivery_id} остановлено.\n"
        f"📍 Координаты больше не передаются.\n"
        f"Нажмите «Возобновить», чтобы продолжить.",
        reply_markup=reply_markup
    )