# bot.py
"""Точка входа в приложение: инициализация и запуск бота."""
import logging
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from aiokafka import AIOKafkaProducer
import asyncpg

from config import BOT_TOKEN, DB_CONFIG, KAFKA_BOOTSTRAP
from core.db import setup_db, close_db
from handlers.navigation import start_cmd, cancel_cmd, callback_router, text_router
from handlers.location_handler import handle_location_update
from handlers.location_handler import handle_location_update
from handlers.order_handler import select_delivery_callback
from handlers.tracking_handler import start_tracking_callback, complete_order_callback, stop_tracking_callback

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

async def setup_services(application):
    """Инициализация БД и Kafka Producer при старте бота."""
    # 1. Пул БД
    try:
        pool = await asyncpg.create_pool(**DB_CONFIG, min_size=1, max_size=5)
        application.bot_data["db_pool"] = pool
        logger.info("✅ PostgreSQL подключён")
    except Exception as e:
        logger.error(f"❌ Ошибка БД: {e}")
        application.bot_data["db_pool"] = None

    # 2. Kafka Producer
    try:
        producer = AIOKafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            compression_type="lz4",
            acks="all",
            enable_idempotence=True
        )
        await producer.start()
        application.bot_data["kafka_producer"] = producer
        logger.info("✅ Kafka Producer запущен")
    except Exception as e:
        logger.error(f"❌ Ошибка Kafka Producer: {e}")
        application.bot_data["kafka_producer"] = None
        
async def close_services(application):
    """Корректное закрытие соединений."""
    pool = application.bot_data.get("db_pool")
    if pool:
        await pool.close()
        logger.info("🔌 PostgreSQL закрыт")
        
    producer = application.bot_data.get("kafka_producer")
    if producer:
        await producer.stop()
        logger.info("🔌 Kafka Producer остановлен")

def main() -> None:
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.post_init = setup_services
    app.post_shutdown = close_services
    
    # === 1. Выбор заказа (исправлен паттерн!) ===
    app.add_handler(CallbackQueryHandler(select_delivery_callback, pattern="^order:select:"))
    
    # === 2. Кнопка "Начать заказ" (оставляем как есть) ===
    app.add_handler(CallbackQueryHandler(start_tracking_callback, pattern="^start_tracking$"))
    app.add_handler(CallbackQueryHandler(complete_order_callback, pattern="^order:complete:"))
    app.add_handler(CallbackQueryHandler(stop_tracking_callback, pattern="^order:stop:"))
    
    # === 3. Геопозиция — ОДИН хендлер, без дубликатов ===
    # В PTB v20+ filters.LOCATION уже ловит и новые, и отредактированные сообщения
    app.add_handler(MessageHandler(filters.LOCATION, handle_location_update))
    
    # === 4. Остальные хендлеры ===
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))
    
    logger.info("✅ Бот запущен.")
    app.run_polling()


if __name__ == '__main__':
    main()