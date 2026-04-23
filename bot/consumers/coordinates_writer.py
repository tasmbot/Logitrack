# consumers/coordinates_writer.py
import asyncio
import asyncpg
import json
import logging
import signal
from datetime import datetime
from decimal import Decimal
from aiokafka import AIOKafkaConsumer
from pydantic import BaseModel, ValidationError

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


KAFKA_BOOTSTRAP = "127.0.0.1:9092"
KAFKA_TOPIC =  "courier.coordinates"
GROUP_ID = "coordinates-db-writer"
DB_DSN = "postgresql://postgres:admin@localhost:5432/logitrack"
BATCH_SIZE = 50
BATCH_TIMEOUT = 5.0

class CoordMessage(BaseModel):
    delivery_id: int
    lat: float
    lng: float
    accuracy: float = 0.0
    ts: str
    courier_id: int

    def validate_coords(self):
        if not (-90 <= self.lat <= 90) or not (-180 <= self.lng <= 180):
            raise ValueError("Недопустимые координаты")

shutdown_event = asyncio.Event()
batch_buffer = []
batch_lock = asyncio.Lock()
db_pool = None

def _serialize_for_db(data):
    if isinstance(data, Decimal): return float(data)
    if isinstance(data, datetime): return data.isoformat()
    return data

async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DB_DSN, min_size=1, max_size=5)
    logger.info("✅ Пул БД создан")

async def flush_to_db(records):
    if not records or not db_pool: return
    values = []
    for r in records:
        values.extend([r.delivery_id, r.lat, r.lng])
    placeholders = ", ".join(f"(${i*3+1}, ${i*3+2}, ${i*3+3})" for i in range(len(records)))
    query = f"""
        INSERT INTO delivery_coordinates (delivery_id, latitude, longitude)
        VALUES {placeholders}
        """
        # ON CONFLICT (delivery_id) DO UPDATE SET
        #     latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude
    
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(query, *values)
        logger.info(f"📦 Записано точек в БД: {len(records)}")
    except Exception as e:
        logger.error(f"❌ Ошибка записи в БД: {e}")

async def batch_flusher():
    while not shutdown_event.is_set():
        await asyncio.sleep(BATCH_TIMEOUT)
        async with batch_lock:
            if batch_buffer:
                to_flush = batch_buffer[:]
                batch_buffer.clear()
                await flush_to_db(to_flush)

async def run_consumer():
    await init_db()
    consumer = AIOKafkaConsumer(
        KAFKA_TOPIC, bootstrap_servers=KAFKA_BOOTSTRAP, group_id=GROUP_ID,
        enable_auto_commit=False, max_poll_records=100, fetch_max_wait_ms=500
    )
    await consumer.start()
    logger.info(f"👂 Подписка на топик: {KAFKA_TOPIC}")
    flush_task = asyncio.create_task(batch_flusher())

    try:
        while not shutdown_event.is_set():
            msg_batch = await consumer.getmany(timeout_ms=1000)
            for tp, messages in msg_batch.items():
                for msg in messages:
                    try:
                        payload = json.loads(msg.value.decode())
                        coord = CoordMessage(**payload)
                        coord.validate_coords()
                        async with batch_lock:
                            batch_buffer.append(coord)
                            if len(batch_buffer) >= BATCH_SIZE:
                                to_flush = batch_buffer[:]
                                batch_buffer.clear()
                                await flush_to_db(to_flush)
                    except (ValidationError, json.JSONDecodeError, Exception) as e:
                        logger.warning(f"⚠️ Пропущено сообщение: {e}")
                await consumer.commit()
    finally:
        await consumer.stop()
        flush_task.cancel()
        if db_pool: await db_pool.close()
        logger.info("✅ Консьюмер остановлен")

if __name__ == "__main__":
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda s, f: (logger.info("🛑 Остановка..."), shutdown_event.set()))
    try: asyncio.run(run_consumer())
    except KeyboardInterrupt: shutdown_event.set()