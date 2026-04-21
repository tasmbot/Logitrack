# core/db.py
import logging
import asyncpg
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def setup_db(application):
    """Инициализация пула соединений и создание таблиц при старте."""
    from config import DB_CONFIG
    
    try:
        pool = await asyncpg.create_pool(**DB_CONFIG, min_size=1, max_size=5)
        application.bot_data["db_pool"] = pool
        logger.info("✅ Подключение к PostgreSQL успешно")
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
        application.bot_data["db_pool"] = None


async def close_db(application):
    """Закрытие пула соединений при остановке бота."""
    pool = application.bot_data.get("db_pool")
    if pool:
        await pool.close()
        logger.info("🔌 Соединение с PostgreSQL закрыто")


def get_pool(context: ContextTypes.DEFAULT_TYPE):
    """Получение пула соединений из контекста приложения."""
    return context.bot_data.get("db_pool")


async def fetch_table_columns(pool, table_name: str, schema: str = "public") -> list[str]:
    """Получение списка колонок таблицы из information_schema."""
    async with pool.acquire() as conn:
        result = await conn.fetch(
            """
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = $1 AND table_schema = $2 
            ORDER BY ordinal_position
            """,
            table_name, schema
        )
    return [row["column_name"] for row in result]


async def fetch_one_row(pool, table_name: str, columns: list[str], limit: int = 1):
    """Выполнение SELECT с ограничением и возврат первой строки."""
    cols_str = ", ".join(f'"{c}"' for c in columns)
    query = f'SELECT {cols_str} FROM "{table_name}" LIMIT $1'
    
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, limit)


async def insert_row(pool, table_name: str, columns: list[str], values: list):
    """Безопасная вставка строки с возвратом вставленных данных."""
    if not columns or not values or len(columns) != len(values):
        raise ValueError("Количество колонок и значений должно совпадать")
    
    col_names = ", ".join(f'"{c}"' for c in columns)
    placeholders = ", ".join(f"${i+1}" for i in range(len(values)))
    query = f'INSERT INTO "{table_name}" ({col_names}) VALUES ({placeholders}) RETURNING *'
    
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, *values)
    
async def get_courier_info(pool, user_id: int):
    """
    Получение courier_id и проверка role_id по user_id.
    
    Returns:
        dict с courier_id, role_id или None если не курьер.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT u.role_id, c.courier_id, CONCAT(u.first_name, ' ', u.last_name) as courier_name, c.active
            FROM users u
            LEFT JOIN couriers c ON u.user_id = c.user_id
            WHERE u.user_id = $1
        """, user_id)
        
        if not row:
            return None
        
        return {
            "role_id": row["role_id"],
            "courier_id": row["courier_id"],
            "courier_name": row["courier_name"],
            "is_active_courier": row["active"] and row["courier_id"] is not None
        }


async def get_courier_active_deliveries(pool, courier_id: int, limit: int = 20):
    """
    Получение списка активных доставок для курьера.
    
    Returns:
        List[dict] с данными заказа.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT 
                d.delivery_id,
                o.order_id,
                s.status_name,
                o.created_at,
                l.address as pickup_address,
                o.total_price
            FROM deliveries d
            JOIN orders o ON d.order_id = o.order_id
            JOIN statuses s ON o.status_id = s.status_id
            JOIN locations l ON d.location_id = l.location_id
            WHERE d.courier_id = $1 
              AND d.actual_delivery_datetime IS NULL
              AND s.status_name NOT IN ('cancelled', 'delivered', 'refunded')
            ORDER BY o.created_at DESC
            LIMIT $2
        """, courier_id, limit)
        
        return [dict(row) for row in rows]


async def save_delivery_coordinate(pool, delivery_id: int, latitude: float, longitude: float):
    """
    Сохранение или обновление координат доставки.
    Использует UPSERT: если запись есть — обновляет, если нет — создаёт.
    """
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO delivery_coordinates (delivery_id, latitude, longitude)
            VALUES ($1, $2, $3)
            ON CONFLICT (delivery_id) 
            DO UPDATE SET 
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude
        """, delivery_id, latitude, longitude)
        
async def update_order_status(pool, delivery_id: int, status_id: int):
    """
    Обновляет статус заказа, связанного с доставкой.
    Меняет orders.status_id и фиксирует время изменения.
    """
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE orders
            SET status_id = $1
            WHERE order_id = (
                SELECT order_id FROM deliveries WHERE delivery_id = $2
            )
        """, status_id, delivery_id)