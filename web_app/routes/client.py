# routes/client.py
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
import asyncio
import logging
import csv, io, math, random

from core.db import get_pool

router = APIRouter(prefix="/client", tags=["Клиент"])
logger = logging.getLogger(__name__)

def _ensure_client(request: Request):
    if request.session.get("role_id") != 4:
        raise HTTPException(status_code=403, detail="Доступ запрещён")

async def _resolve_client_id(request: Request) -> int:
    user_id = request.session.get("user_id")
    if not user_id: raise HTTPException(status_code=401, detail="Не авторизован")
    pool = get_pool(request)
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT client_id FROM clients WHERE user_id = $1", user_id)
    if not row: raise HTTPException(status_code=404, detail="Профиль клиента не найден")
    return row["client_id"]

async def _recalculate_route_background(pool, courier_id: int):
    """
    Фоновая задача: вызывает SQL-функцию пересчёта маршрута курьера.
    Выполняется ВНЕ основной транзакции создания заказа.
    """
    # Небольшая задержка гарантирует, что основная транзакция успела закоммититься
    await asyncio.sleep(1.5)
    try:
        async with pool.acquire() as conn:
            await conn.execute("SELECT recalculate_courier_route($1)", courier_id)
            logger.info(f"✅ Маршрут курьера #{courier_id} успешно оптимизирован")
    except Exception as e:
        logger.error(f"❌ Ошибка фонового пересчёта маршрута курьера #{courier_id}: {e}")


@router.get("/api/orders")
async def get_orders(request: Request):
    _ensure_client(request)
    client_id = await _resolve_client_id(request)
    pool = get_pool(request)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT o.order_id, l.address as delivery_location, s.status_name,
                   o.total_price, to_char(o.created_at, 'DD-MM-YYYY HH24:MI') as created_at, 
                   COALESCE(string_agg(i.item_name || ' x' || oi.ordered_quantity, ', '), '') as items
            FROM orders o
            JOIN statuses s ON o.status_id = s.status_id
            LEFT JOIN order_items oi ON o.order_id = oi.order_id
            LEFT JOIN items i ON oi.item_id = i.item_id
            LEFT JOIN deliveries d ON o.order_id = d.order_id
            LEFT JOIN locations l ON d.location_id = l.location_id
            WHERE o.client_id = $1
            GROUP BY o.order_id, l.address, s.status_name, o.total_price, o.created_at
            ORDER BY o.created_at DESC
            LIMIT 100
        """, client_id)
    return [dict(r) for r in rows]

@router.get("/api/orders/export")
async def export_orders(request: Request):
    _ensure_client(request)
    client_id = await _resolve_client_id(request)
    pool = get_pool(request)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT o.order_id, l.address as delivery_location, s.status_name,
                   o.total_price, o.created_at
            FROM orders o
            JOIN statuses s ON o.status_id = s.status_id
            LEFT JOIN deliveries d ON o.order_id = d.order_id
            LEFT JOIN locations l ON d.location_id = l.location_id
            WHERE o.client_id = $1
            ORDER BY o.created_at DESC
        """, client_id)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Заказ", "Адрес доставки", "Статус", "Сумма", "Дата"])
    for r in rows:
        writer.writerow([r["order_id"], r["delivery_location"] or "-", r["status_name"], r["total_price"], r["created_at"]])

    response = StreamingResponse(iter([output.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=orders_report.csv"
    return response

@router.get("/create")
async def create_order_page(request: Request):
    _ensure_client(request)
    pool = get_pool(request)
    client_id = await _resolve_client_id(request)
    
    async with pool.acquire() as conn:
        # 1. Адрес клиента
        profile = await conn.fetchrow(
            """SELECT c.address, l.location_id 
            FROM clients c
            JOIN locations l ON c.address = l.address
            WHERE client_id = $1""", client_id
        )
        has_address = bool(profile and profile["address"])
        
        # 2. Если адрес есть — находим ближайший магазин
        available_items = []
        if has_address and profile["location_id"]:
            # Координаты клиента
            client_loc = await conn.fetchrow(
                "SELECT latitude, longitude FROM locations WHERE location_id = $1",
                profile["location_id"]
            )
            
            if client_loc and client_loc["latitude"] and client_loc["longitude"]:
                # Все магазины
                stores = await conn.fetch("""
                    SELECT location_id, latitude, longitude 
                    FROM locations 
                    WHERE location_type_id = (
                        SELECT location_type_id FROM location_types WHERE location_type = 'store'
                    )
                """)
                
                # Поиск ближайшего
                nearest = None
                min_dist = float("inf")
                c_lat, c_lng = float(client_loc["latitude"]), float(client_loc["longitude"])
                
                for s in stores:
                    if s["latitude"] and s["longitude"]:
                        dist = math.hypot(float(s["latitude"]) - c_lat, float(s["longitude"]) - c_lng)
                        if dist < min_dist:
                            min_dist = dist
                            nearest = s
                
                # 3. Если магазин найден — загружаем товары с остатками
                if nearest:
                    store_id = nearest["location_id"]
                    items_with_stock = await conn.fetch("""
                        SELECT 
                            i.item_id,
                            i.item_name,
                            i.price,
                            COALESCE(ss.quantity, 0) AS available_qty
                        FROM items i
                        LEFT JOIN store_stock ss ON i.item_id = ss.item_id AND ss.location_id = $1
                        WHERE COALESCE(ss.quantity, 0) > 0  -- Показываем только товары в наличии
                        ORDER BY i.item_name
                    """, store_id)
                    
                    available_items = [dict(i) for i in items_with_stock]
        else:
            # Фолбэк: все товары (для пользователей без адреса)
            all_items = await conn.fetch("SELECT item_id, item_name, price FROM items ORDER BY item_name")
            available_items = [dict(i) for i in all_items]

    return request.app.state.templates.TemplateResponse(
        "create_order.html",
        {
            "request": request, 
            "items": available_items,  # Теперь с available_qty
            "has_address": has_address,
            "nearest_store_found": bool(nearest) if has_address else False  # Для отображения инфо
        }
    )

@router.post("/orders")
async def submit_order(request: Request):
    _ensure_client(request)
    pool = get_pool(request)
    if not pool:
        raise HTTPException(status_code=503, detail="БД недоступна")

    data = await request.json()
    cart = data.get("cart", [])
    
    comment = data.get("comment", "")
    if not cart:
        raise HTTPException(status_code=400, detail="Корзина пуста")

    client_id = await _resolve_client_id(request)

    async with pool.acquire() as conn:
        # 1. Адрес клиента
        profile = await conn.fetchrow("SELECT address FROM clients WHERE client_id = $1", client_id)
        if not profile or not profile["address"]:
            raise HTTPException(status_code=400, detail="Укажите адрес в профиле")
        address = profile["address"]

        # 2. Найти/создать локацию доставки
        loc = await conn.fetchrow("SELECT location_id FROM locations WHERE address = $1", address)
        if not loc:
            type_id_res = await conn.fetchrow(
                "SELECT location_type_id FROM location_types WHERE location_type = 'delivery_point'"
            )
            if not type_id_res:
                raise HTTPException(status_code=500, detail="Нет типа локации")
            lat, lng = round(random.uniform(55.0, 56.0), 6), round(random.uniform(36.0, 37.0), 6)
            loc = await conn.fetchrow(
                "INSERT INTO locations (location_type_id, address, latitude, longitude) "
                "VALUES ($1, $2, $3, $4) RETURNING location_id",
                type_id_res["location_type_id"], address, lat, lng
            )
        location_id = loc["location_id"]

        # 3. Ближайший магазин
        stores = await conn.fetch(
            "SELECT location_id, latitude, longitude FROM locations "
            "JOIN location_types USING(location_type_id) WHERE location_type = 'store'"
        )
        if not stores:
            raise HTTPException(status_code=404, detail="Нет магазинов")
        
        d_coords = await conn.fetchrow(
            "SELECT latitude, longitude FROM locations WHERE location_id = $1", location_id
        )
        dlat, dlng = float(d_coords["latitude"]), float(d_coords["longitude"])

        nearest = None
        min_dist = float("inf")
        for s in stores:
            if s["latitude"] and s["longitude"]:
                dist = math.hypot(float(s["latitude"]) - dlat, float(s["longitude"]) - dlng)
                if dist < min_dist:
                    min_dist = dist
                    nearest = s
        if not nearest:
            raise HTTPException(status_code=500, detail="Нет магазинов с координатами")

        store_location_id = nearest["location_id"]

        # 4. Проверка остатков и создание заказа
        total_price = 0.0
        for item in cart:
            stock = await conn.fetchval(
                "SELECT quantity FROM store_stock WHERE location_id = $1 AND item_id = $2",
                store_location_id, item["id"]
            )
            if not stock or stock < item["qty"]:
                raise HTTPException(status_code=400, detail=f"Недостаточно товара ID {item['id']}")
            
            price = await conn.fetchval("SELECT price FROM items WHERE item_id = $1", item["id"])
            total_price += float(price or 0) * item["qty"]

        order = await conn.fetchrow(
            "INSERT INTO orders (client_id, status_id, comments, total_price) "
            "VALUES ($1, 1, $2, $3) RETURNING order_id",
            client_id, comment, total_price
        )
        order_id = order["order_id"]

        for item in cart:
            await conn.execute(
                "INSERT INTO order_items (order_id, item_id, ordered_quantity) VALUES ($1, $2, $3)",
                order_id, item["id"], item["qty"]
            )

        # 5. Назначение доставки
        # courier = await conn.fetchrow("SELECT courier_id FROM couriers WHERE active = true ORDER BY RANDOM() LIMIT 1")
        # if not courier:
        #     raise HTTPException(status_code=400, detail="Нет свободных курьеров")
        
        courier_id =  5797 #courier["courier_id"]

        # Создаём базовый маршрут (оптимизатор объединит его с другими активными маршрутами курьера)
        route = await conn.fetchrow("INSERT INTO routes (name) VALUES ($1) RETURNING route_id", " ")
        route_id = route["route_id"]
        await conn.execute("UPDATE routes SET name = $1 WHERE route_id = $2", f"Route_{route_id}", route_id)

        # ВСТАВКА С pickup_location_id (обязательно для работы оптимизатора)
        await conn.execute(
            "INSERT INTO deliveries (order_id, courier_id, route_id, location_id, pickup_location_id) "
            "VALUES ($1, $2, $3, $4, $5)",
            order_id, courier_id, route_id, location_id, store_location_id
        )

    # 6. Асинхронный вызов пересчёта (ВНЕ транзакции!)
    try:
        asyncio.create_task(_recalculate_route_background(pool, courier_id))
    except Exception as e:
        logger.warning(f"⚠️ Не удалось запустить фоновый пересчёт маршрута: {e}")

    return JSONResponse(content={"status": "ok", "order_id": order_id})