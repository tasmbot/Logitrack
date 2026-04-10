# handlers/location_handler.py
import logging
import json
from datetime import datetime, timezone
from telegram import Update
from telegram.ext import ContextTypes
from aiokafka.errors import KafkaError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup

from core.context import FlowManager
from config import KAFKA_COORD_TOPIC

logger = logging.getLogger(__name__)

async def handle_location_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message or update.edited_message
    if not message or not message.location:
        return

    logger.info(f"📍 Получены координаты: {message.location.latitude}, {message.location.longitude}")
    logger.info(f"   tracking_active={FlowManager.is_tracking_active(context)}, location_shared={FlowManager.is_location_shared(context)}")

    if FlowManager.is_tracking_active(context):
        logger.info("📤 Отправка в Kafka (режим отслеживания)")
        await _send_coords_to_kafka(update, context, message.location)
        return

    if not FlowManager.is_location_shared(context):
        logger.info("🔑 Первое получение геопозиции — ставим флаг и показываем кнопку")
        FlowManager.set_location_shared(context, True)
        
        delivery_id = FlowManager.get_delivery(context)
        if delivery_id:
            keyboard = [[InlineKeyboardButton("🚀 Начать заказ", callback_data="start_tracking")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await message.reply_text(
                f"✅ Геопозиция получена!\n"
                f"Теперь вы можете приступить к заказу #{delivery_id}.",
                reply_markup=reply_markup
            )
        else:
            await message.reply_text("✅ Геопозиция получена. Сначала выберите заказ в меню.")
    else:
        logger.info("⏭ Геопозиция уже была получена ранее — игнорируем (ждём нажатия кнопки)")

async def _send_coords_to_kafka(update: Update, context: ContextTypes.DEFAULT_TYPE, loc):
    """Внутренняя функция отправки в Kafka (вызывается только при active=True)"""
    delivery_id = FlowManager.get_delivery(context)
    # courier_id = context.user_data.get("courier_id")  # или из FlowManager
    courier_id = FlowManager.get_courier_id(context)
    producer = context.bot_data.get("kafka_producer")

    if courier_id is None:
        # Вариант А: взять из сессии Telegram (если курьер логинился в боте)
        courier_id = context.user_data.get("courier_id")
        
    if courier_id is None:
        logger.warning("⚠️ courier_id отсутствует в контексте. Координата будет сохранена без привязки к курьеру.")
 

    if not producer or not delivery_id:
        return

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
    except KafkaError as e:
        logger.error(f"❌ Ошибка Kafka: {e}")