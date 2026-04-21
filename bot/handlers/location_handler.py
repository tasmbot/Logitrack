# handlers/location_handler.py
import logging
import json
from datetime import datetime, timezone
from telegram import Update
from telegram.ext import ContextTypes
from aiokafka.errors import KafkaError
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from core.context import FlowManager
from config import KAFKA_COORD_TOPIC

logger = logging.getLogger(__name__)

async def handle_location_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message or update.edited_message
    if not message or not message.location:
        return

    delivery_id = FlowManager.get_delivery(context)
    is_tracking = FlowManager.is_tracking_active(context)

    # 1. Трекинг активен → отправка в Kafka
    if is_tracking and delivery_id:
        await _send_coords_to_kafka(update, context, message.location)
        return

    # 2. Трекинг не активен, но заказ выбран → предлагаем начать
    if not is_tracking and delivery_id:
        # Показываем кнопку только при НОВОМ сообщении (не edited_message), чтобы не спамить
        if update.edited_message is None:
            keyboard = [[InlineKeyboardButton("🚀 Начать заказ", callback_data=f"order:start:{delivery_id}")]]
            await message.reply_text(
                "📍 Геопозиция получена. Для начала работы нажмите кнопку:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return

    # 3. Заказ не выбран
    if update.edited_message is None:
        await message.reply_text(
            "⚠️ Сначала выберите заказ в меню «Мои заказы».",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📦 Мои заказы", callback_data="order:menu")]])
        )
        
async def _send_coords_to_kafka(update: Update, context: ContextTypes.DEFAULT_TYPE, loc):
    """Отправка координат в Kafka."""
    delivery_id = FlowManager.get_delivery(context)
    courier_id = FlowManager.get_courier_id(context)
    producer = context.bot_data.get("kafka_producer")

    if not producer or not delivery_id:
        return
    
    # Если courier_id не в контексте, пробуем взять из сессии
    if not courier_id:
        courier_id = context.user_data.get("courier_id")

    payload = {
        "delivery_id": delivery_id,
        "courier_id": courier_id,
        "lat": loc.latitude,
        "lng": loc.longitude,
        "accuracy": loc.horizontal_accuracy or 0.0,
        "ts": datetime.now(timezone.utc).isoformat()
    }

    try:
        await producer.send_and_wait(
            topic=KAFKA_COORD_TOPIC,
            key=str(delivery_id).encode(),
            value=json.dumps(payload).encode()
        )
        # Логируем тихо, чтобы не спамить в чат
        logger.debug(f"📤 Kafka: delivery={delivery_id}")
    except KafkaError as e:
        logger.error(f"❌ Ошибка Kafka: {e}")