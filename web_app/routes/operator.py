# routes/operator.py
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from datetime import datetime
from decimal import Decimal
import json
import csv
import io
import logging
from datetime import timedelta

from core.db import get_pool

router = APIRouter(prefix="/operator", tags=["Оператор"])
logger = logging.getLogger(__name__)

class RouteReorderRequest(BaseModel):
    new_order: list[int]

def _serialize_for_json(data):
    """
    Рекурсивно преобразует datetime и Decimal в JSON-совместимые типы.
    """
    if isinstance(data, datetime):
        return data.isoformat()
    elif isinstance(data, Decimal):
        return float(data)  # используйте str(data), если важна точность до копейки
    elif isinstance(data, dict):
        return {k: _serialize_for_json(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_serialize_for_json(item) for item in data]
    return data

# === Проверка роли (внутренняя утилита для MVP) ===
def _ensure_operator(request: Request):
    if request.session.get("role_id") != 2:
        raise HTTPException(status_code=403, detail="Доступ запрещён")

# === API для таблиц и графиков ===
@router.get("/api/orders")
async def get_orders(request: Request):
    _ensure_operator(request)
    pool = get_pool(request)
    if not pool:
        return JSONResponse(content=[])
    
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT o.order_id, CONCAT(u.first_name, ' ', u.last_name) as client_name, u.phone as client_phone,
                   l.address as delivery_location, CONCAT('₽ ', o.total_price::numeric) as total_price, s.status_name, s.status_id,
                   to_char(o.created_at, 'DD-MM-YYYY HH24:MI') as created_at
            FROM orders o
            JOIN clients c ON o.client_id = c.client_id
            JOIN users u ON c.user_id = u.user_id
            LEFT JOIN deliveries d ON o.order_id = d.order_id
            LEFT JOIN locations l ON d.location_id = l.location_id
            JOIN statuses s ON o.status_id = s.status_id
            ORDER BY o.created_at DESC
            LIMIT 100
        """)
    return [dict(r) for r in rows]

@router.get("/api/statuses")
async def get_statuses(request: Request):
    _ensure_operator(request)
    pool = get_pool(request)
    if not pool:
        return JSONResponse(content=[])
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT status_id, status_name FROM statuses ORDER BY status_id")
    return [{"id": r["status_id"], "name": r["status_name"]} for r in rows]

@router.patch("/api/orders/{order_id}/status")
async def update_order_status(request: Request, order_id: int, new_status_id: int):
    _ensure_operator(request)
    pool = get_pool(request)
    if not pool:
        raise HTTPException(status_code=503, detail="БД недоступна")
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE orders SET status_id = $1, updated_at = CURRENT_TIMESTAMP WHERE order_id = $2",
            new_status_id, order_id
        )
    return JSONResponse(content={"status": "ok"})

@router.delete("/api/orders/{order_id}")
async def delete_order(request: Request, order_id: int):
    _ensure_operator(request)
    pool = get_pool(request)
    if not pool:
        raise HTTPException(status_code=503)
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM orders WHERE order_id = $1", order_id)
    return JSONResponse(content={"status": "ok"})

@router.get("/api/analytics")
async def get_analytics(request: Request):
    _ensure_operator(request)
    pool = get_pool(request)
    if not pool:
        return JSONResponse(content={})
    
    async with pool.acquire() as conn:
        # 1. Загрузка курьеров
        couriers = await conn.fetch("""
            SELECT c.courier_id, CONCAT(u.first_name, ' ', u.last_name) as name, COUNT(d.delivery_id) as active_deliveries
            FROM couriers c
            JOIN users u ON c.user_id = u.user_id
            LEFT JOIN deliveries d ON c.courier_id = d.courier_id
            LEFT JOIN orders o ON d.order_id = o.order_id
            LEFT JOIN statuses s ON o.status_id = s.status_id
            WHERE s.status_name IN ('created', 'in_transit')
            GROUP BY c.courier_id, CONCAT(u.first_name, ' ', u.last_name)
            ORDER BY active_deliveries DESC
            LIMIT 7
        """)
        # 2. Распределение заказов по статусам (за 30 дней)
        statuses = await conn.fetch("""
            SELECT s.status_name, COUNT(o.order_id) as cnt
            FROM orders o
            JOIN statuses s ON o.status_id = s.status_id
            WHERE o.created_at >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY s.status_name
            ORDER BY cnt DESC
        """)
        # 3. SLA-мониторинг (факт vs план за 14 дней)
        sla_data = await conn.fetch("""
            SELECT 
                DATE(o.created_at)::text as order_date,
                AVG(EXTRACT(EPOCH FROM (d.actual_delivery_datetime - o.created_at))/3600)::float as avg_hours
            FROM orders o
            JOIN deliveries d ON o.order_id = d.order_id
            WHERE d.actual_delivery_datetime IS NOT NULL
              AND o.created_at >= CURRENT_DATE - INTERVAL '14 days'
            GROUP BY DATE(o.created_at)
            ORDER BY order_date
        """)
    return {
        "couriers": [{"id": r["courier_id"], "name": r["name"], "active_deliveries": r["active_deliveries"]} for r in couriers],
        "statuses": [dict(r) for r in statuses],
        "sla": [dict(r) for r in sla_data]
    }

@router.get("/api/orders/export")
async def export_orders_csv(request: Request):
    _ensure_operator(request)
    pool = get_pool(request)
    if not pool: raise HTTPException(status_code=503)

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT o.order_id, CONCAT(u.first_name, ' ', u.last_name) as client_name, u.phone as client_phone,
                   l.address as delivery_location, o.total_price, s.status_name, o.created_at
            FROM orders o
            JOIN clients c ON o.client_id = c.client_id
            JOIN users u ON c.user_id = u.user_id
            LEFT JOIN deliveries d ON o.order_id = d.order_id
            LEFT JOIN locations l ON d.location_id = l.location_id
            JOIN statuses s ON o.status_id = s.status_id
            ORDER BY o.created_at DESC
            LIMIT 1000
        """)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Клиент", "Телефон", "Адрес", "Сумма", "Статус", "Дата"])
    for r in rows:
        writer.writerow([r["order_id"], r["client_name"], r["client_phone"], 
                         r["delivery_location"] or "-", r["total_price"], 
                         r["status_name"], r["created_at"]])

    response = StreamingResponse(iter([output.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=operator_orders_export.csv"
    return response

@router.get("/couriers/{courier_id}/route")
async def operator_courier_route_page(request: Request, courier_id: int):
    _ensure_operator(request)
    pool = get_pool(request)
    if not pool: raise HTTPException(status_code=503, detail="БД недоступна")

    async with pool.acquire() as conn:
        courier_info = await conn.fetchrow(
            "SELECT CONCAT(u.first_name, ' ', u.last_name) as full_name FROM couriers c JOIN users u ON c.user_id = u.user_id WHERE c.courier_id = $1",
            courier_id
        )
        if not courier_info:
            raise HTTPException(status_code=404, detail="Курьер не найден")

        delivery = await conn.fetchrow("""
            SELECT d.delivery_id, r.route_id 
            FROM deliveries d JOIN routes r ON d.route_id = r.route_id
            WHERE d.courier_id = $1 AND d.actual_delivery_datetime IS NULL
            ORDER BY 1 DESC LIMIT 1
        """, courier_id)

        points = []
        if delivery:
            points = await conn.fetch("""
                SELECT 
                    rp.sequence_num,
                    l.location_id,
                    l.address,
                    l.latitude::float AS latitude, 
                    l.longitude::float AS longitude,
                    lt.location_type,
                    rp.expected_arrival_time, 
                    rp.actual_arrival_time
                FROM route_points rp
                JOIN locations l ON rp.location_id = l.location_id
                JOIN location_types lt ON l.location_type_id = lt.location_type_id
                WHERE rp.route_id = $1
                ORDER BY rp.sequence_num
            """, delivery["route_id"])

        orders = await conn.fetch("""
            SELECT o.order_id, CONCAT(u.first_name, ' ', u.last_name) AS client_name, u.phone AS client_phone,
                   l.address AS delivery_address, COALESCE(o.total_weight, 0) AS total_weight,
                   s.status_name, to_char(o.created_at, 'DD-MM-YYYY HH24:MI') AS created_at
            FROM deliveries d
            JOIN orders o ON d.order_id = o.order_id
            JOIN statuses s ON o.status_id = s.status_id
            JOIN clients c ON o.client_id = c.client_id
            JOIN users u ON c.user_id = u.user_id
            LEFT JOIN locations l ON d.location_id = l.location_id
            WHERE d.courier_id = $1
              AND s.status_name IN ('created', 'in_transit', 'assigned', 'on_the_way')
            ORDER BY o.created_at DESC
        """, courier_id)

    route_id = delivery["route_id"] if delivery else None

    # сериализуем datetime/Decimal перед передачей в шаблон
    return request.app.state.templates.TemplateResponse(
        "operator_courier_view.html",
        {
            "request": request,
            "courier_name": courier_info["full_name"],
            "courier_id": courier_id,
            "route_id": route_id,
            "orders": _serialize_for_json([dict(o) for o in orders]),
            "points": _serialize_for_json([dict(p) for p in points])
        }
    )


@router.get("/api/audit")
async def get_audit_log(request: Request, limit: int = 50):
    _ensure_operator(request)
    pool = get_pool(request)
    if not pool:
        return JSONResponse(content=[])

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT to_char(a.changed_at, 'DD-MM-YYYY HH24:MI') as changed_at, CONCAT(u.first_name, ' ', u.last_name) as user_name, a.table_name, 
                   a.record_id, a.action, a.old_values, a.new_values
            FROM audit_log a
            LEFT JOIN users u ON a.user_id = u.user_id
            ORDER BY a.changed_at DESC
            LIMIT $1
        """, limit)

    result = []
    for r in rows:
        # asyncpg возвращает jsonb как dict, но на всякий случай обрабатываем и строки
        old_d = r["old_values"] or {}
        new_d = r["new_values"] or {}
        if isinstance(old_d, str): old_d = json.loads(old_d) if old_d else {}
        if isinstance(new_d, str): new_d = json.loads(new_d) if new_d else {}

        # Находим все ключи, которые изменились
        all_keys = sorted(set(list(old_d.keys()) + list(new_d.keys())))
        changed_keys = [k for k in all_keys if old_d.get(k) != new_d.get(k)]

        # Формируем строки вида "key1=val1, key2=val2"
        old_str = ", ".join(f"{k}={old_d[k]}" for k in changed_keys if k in old_d) or "-"
        new_str = ", ".join(f"{k}={new_d[k]}" for k in changed_keys if k in new_d) or "-"

        result.append({
            "changed_at": r["changed_at"],
            "user_name": r["user_name"],
            "table_name": r["table_name"],
            "record_id": r["record_id"],
            "action": r["action"],
            "old_values": old_str,
            "new_values": new_str
        })
        
    return result

@router.get("/orders/{order_id}/detail")
async def order_detail_page(request: Request, order_id: int):
    """Страница с детальной информацией о заказе (только для оператора)."""
    role = request.session.get("role_id")
    if role not in (2, 3, 4):
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    pool = get_pool(request)
    if not pool: raise HTTPException(status_code=503, detail="БД недоступна")

    async with pool.acquire() as conn:
        # 1. Основная информация
        order = await conn.fetchrow("""
            SELECT o.order_id, o.total_price, o.comments, o.created_at, o.updated_at,
                   CONCAT(u.first_name, ' ', u.last_name) as client_name, u.email as client_email, u.phone as client_phone,
                   s.status_name, l.address as client_address
            FROM orders o
            JOIN clients cl ON o.client_id = cl.client_id
            JOIN users u ON cl.user_id = u.user_id
            JOIN statuses s ON o.status_id = s.status_id
            JOIN deliveries d ON o.order_id = d.order_id
            JOIN locations l ON d.location_id = l.location_id
            WHERE o.order_id = $1
        """, order_id)
        if not order: raise HTTPException(status_code=404, detail="Заказ не найден")

        # 2. Товары
        items = await conn.fetch("""
            SELECT i.item_name, oi.ordered_quantity, i.price, 
                   (oi.ordered_quantity * i.price)::float as subtotal
            FROM order_items oi 
            JOIN items i ON oi.item_id = i.item_id
            WHERE oi.order_id = $1
        """, order_id)

        # 3. Информация о доставке/курьере
        delivery = await conn.fetchrow("""
            WITH latest_coords AS (
                SELECT DISTINCT ON (delivery_id) 
                    delivery_id, latitude, longitude, updated_at
                FROM delivery_coordinates
                ORDER BY delivery_id, updated_at DESC
            )
            SELECT d.delivery_id, CONCAT(u.first_name, ' ', u.last_name) as courier_name,
                u.phone as courier_phone, v.type as vehicle_type, v.license_plate,
                l.latitude as delivery_lat, l.longitude as delivery_lng,
                lc.latitude, lc.longitude, lc.updated_at as coords_updated_at,
                d.expected_delivery_datetime
            FROM deliveries d
            LEFT JOIN couriers co ON d.courier_id = co.courier_id
            LEFT JOIN users u ON co.user_id = u.user_id
            LEFT JOIN locations l ON d.location_id = l.location_id
            LEFT JOIN latest_coords lc ON d.delivery_id = lc.delivery_id
            LEFT JOIN couriers_vehicles cv on cv.courier_id = co.courier_id
            LEFT JOIN vehicles v on v.vehicle_id = cv.vehicle_id
            WHERE d.order_id = $1;
        """, order_id)

        # 4. Расчёт expected_delivery_datetime (если маршрут начат и время ещё не рассчитано)
        expected_delivery_dt = None
        
        vehicle_coefficient = { # коэффициенты для расчета приблизительного времени доставки в зависимости от типа транспорта курьера
                    "car"           : [1.2, 'Автомобиль'],
                    "scooter"       : [2.5, 'Скутер'],
                    "bicycle"       : [3.0, 'Велосипед'],
                    "motorcycle"    : [1.8, 'Мотоцикл'],
                    "van"           : [1.5, 'Минивен'],
                    "truck"         : [1.5, 'Грузовик']
                }
                
        if delivery and delivery.get("latitude") and delivery.get("longitude"):  # координаты курьера
            # Проверяем, что есть координаты точки доставки и время ещё не рассчитано
            if (delivery.get("delivery_lat") and delivery.get("delivery_lng") 
                and delivery.get("coords_updated_at") 
                and not delivery.get("expected_delivery_datetime")):
                
                from core.routing import get_route_geometry
                route_data = await get_route_geometry(
                    lon_start=float(delivery["longitude"]),
                    lat_start=float(delivery["latitude"]),
                    lon_end=float(delivery["delivery_lng"]),
                    lat_end=float(delivery["delivery_lat"])
                )
            
                if route_data and route_data.get("duration_sec"):
                    # Рассчитываем ожидаемое время: время последних координат + длительность маршрута
                    logger.info(f"route_data['duration_sec']: {route_data["duration_sec"]}")
                    expected_delivery_dt = delivery["coords_updated_at"] + timedelta(seconds=route_data["duration_sec"] * vehicle_coefficient.get(delivery['vehicle_type'])[0]) 
                    
                    # Сохраняем в БД (только если ещё не сохранено)
                    await conn.execute(
                        "UPDATE deliveries SET expected_delivery_datetime = $1 WHERE delivery_id = $2",
                        expected_delivery_dt, delivery["delivery_id"]
                    )
            else:
                # Если время уже рассчитано — просто читаем из БД
                expected_delivery_dt = delivery.get("expected_delivery_datetime")
                
        # 5. Получение геометрии маршрута для отображения на карте
        route_geometry = None
        if delivery and delivery.get("latitude") and delivery.get("longitude") and \
           delivery.get("delivery_lat") and delivery.get("delivery_lng"):
            
            from core.routing import get_route_geometry
            route_data = await get_route_geometry(
                lon_start=float(delivery["longitude"]),
                lat_start=float(delivery["latitude"]),
                lon_end=float(delivery["delivery_lng"]),
                lat_end=float(delivery["delivery_lat"])
            )
            
            if route_data:
                # Извлекаем геометрию (если не извлекли ранее для ETA)
                route_geometry = route_data.get("geometry")
                
                # Если ETA ещё не рассчитано — считаем и сохраняем
                if not delivery.get("expected_delivery_datetime") and route_data.get("duration_sec"):
                    expected_delivery_dt = delivery["coords_updated_at"] + timedelta(seconds=route_data["duration_sec"] * vehicle_coefficient.get(delivery['vehicle_type'])[0])
                    await conn.execute(
                        "UPDATE deliveries SET expected_delivery_datetime = $1 WHERE delivery_id = $2",
                        expected_delivery_dt, delivery["delivery_id"]
                    )

        return request.app.state.templates.TemplateResponse(
            "order_detail.html",
            {
                "request": request,
                "order": dict(order),
                "items": [dict(i) for i in items],
                "vehicle": f"{vehicle_coefficient.get(delivery['vehicle_type'])[1]}, {delivery.get('license_plate')}",
                "delivery": {
                    **(dict(delivery) if delivery else {}),
                    "expected_delivery_datetime": expected_delivery_dt
                },
                "route_geometry": route_geometry
            }
        )
    
@router.patch("/routes/{route_id}/reorder")
async def reorder_route_points(
    request: Request,
    route_id: int,
    body: RouteReorderRequest
):
    _ensure_operator(request)
    pool = get_pool(request)
    if not pool:
        raise HTTPException(status_code=503, detail="БД недоступна")

    new_order = body.new_order
    if not new_order:
        raise HTTPException(status_code=400, detail="Пустой список точек")

    async with pool.acquire() as conn:
        delivery = await conn.fetchrow("""
            SELECT d.courier_id, c.user_id as courier_user_id
            FROM deliveries d JOIN couriers c ON d.courier_id = c.courier_id
            WHERE d.route_id = $1 AND d.actual_delivery_datetime IS NULL LIMIT 1
        """, route_id)

        if not delivery:
            raise HTTPException(status_code=404, detail="Маршрут не найден или доставка завершена")

        courier_user_id = delivery["courier_user_id"]

        # 🔒 Атомарное обновление без конфликтов UNIQUE(route_id, sequence_num)
        async with conn.transaction():
            
            web_user_id = request.session.get("user_id")
            if web_user_id:
                # Устанавливаем переменную ТОЛЬКО для этой транзакции
                await conn.execute("SET LOCAL myapp.user_id = $1", str(web_user_id))
            
            # Прямое обновление без промежуточных хаков
            for idx, loc_id in enumerate(new_order, start=1):
                await conn.execute("""
                    UPDATE route_points 
                    SET sequence_num = $1 
                    WHERE route_id = $2 AND location_id = $3
                """, idx, route_id, loc_id)
                
                

    return {"status": "ok", "message": "Порядок точек успешно обновлён"}

