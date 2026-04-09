# handlers/tracking_handler.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from core.context import FlowManager

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

    delivery_id = int(query.data.replace("order:complete:", ""))
    
    # Обновляем статус заказа на "завершён" (зависит от вашей БД, обычно status_id=3)
    pool = context.bot_data.get("db_pool")
    if pool:
        try:
            async with pool.acquire() as conn:
                # Получаем status_id для 'delivered'
                status_id = await conn.fetchval("SELECT status_id FROM statuses WHERE status_name = 'delivered'")
                if status_id:
                    await conn.execute(
                        "UPDATE orders SET status_id = $1 WHERE order_id = (SELECT order_id FROM deliveries WHERE delivery_id = $2)",
                        status_id, delivery_id
                    )
        except Exception as e:
            print(f"❌ Ошибка обновления статуса: {e}")

    # Сбрасываем состояние отслеживания
    FlowManager.reset_delivery_state(context)

    await query.edit_message_text(
        f"✅ Заказ #{delivery_id} завершён!\n"
        f"📍 Отслеживание остановлено. Спасибо за работу!",
        reply_markup=None  # Убираем кнопки
    )

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