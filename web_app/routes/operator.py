# routes/operator.py
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from config import ROLE_NAMES
from datetime import datetime
from decimal import Decimal
import json
import csv
import io

from core.db import get_pool

router = APIRouter(prefix="/operator", tags=["Оператор"])

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
            SELECT o.order_id, u.full_name as client_name, u.phone as client_phone,
                   l.address as delivery_location, o.total_price, s.status_name, s.status_id,
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
            SELECT c.courier_id, u.full_name as name, COUNT(d.delivery_id) as active_deliveries
            FROM couriers c
            JOIN users u ON c.user_id = u.user_id
            LEFT JOIN deliveries d ON c.courier_id = d.courier_id
            LEFT JOIN orders o ON d.order_id = o.order_id
            LEFT JOIN statuses s ON o.status_id = s.status_id
            WHERE s.status_name IN ('created', 'in_transit')
            GROUP BY c.courier_id, u.full_name
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
            SELECT o.order_id, u.full_name as client_name, u.phone as client_phone,
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
    if not pool: raise HTTPException(status_code=503)

    async with pool.acquire() as conn:
        courier_info = await conn.fetchrow("SELECT u.full_name FROM couriers c JOIN users u ON c.user_id = u.user_id WHERE c.courier_id = $1", courier_id)
        if not courier_info: raise HTTPException(status_code=404, detail="Курьер не найден")

        # Активный маршрут
        delivery = await conn.fetchrow("""
            SELECT d.delivery_id, r.route_id FROM deliveries d
            JOIN routes r ON d.route_id = r.route_id
            WHERE d.courier_id = $1 AND d.actual_delivery_datetime IS NULL
            ORDER BY d.updated_at DESC LIMIT 1
        """, courier_id)


        if delivery:
            points = await conn.fetch("""
                SELECT rp.sequence_num, l.address, l.latitude::float AS latitude, 
                       l.longitude::float AS longitude, lt.location_type,
                       rp.expected_arrival_time, rp.actual_arrival_time
                FROM route_points rp
                JOIN locations l ON rp.location_id = l.location_id
                JOIN location_types lt ON l.location_type_id = lt.location_type_id
                WHERE rp.route_id = $1 ORDER BY rp.sequence_num
            """, delivery["route_id"])
        else:
            points = []

        # Заказы этого курьера
        orders = await conn.fetch("""
            SELECT o.order_id, u.full_name AS client_name, u.phone AS client_phone,
                   l.address AS delivery_address, COALESCE(o.total_weight, 0) AS total_weight,
                   s.status_name, o.created_at
            FROM deliveries d
            JOIN orders o ON d.order_id = o.order_id
            JOIN statuses s ON o.status_id = s.status_id
            JOIN clients c ON o.client_id = c.client_id
            JOIN users u ON c.user_id = u.user_id
            LEFT JOIN locations l ON d.location_id = l.location_id
            WHERE d.courier_id = $1
            ORDER BY o.created_at DESC LIMIT 50
        """, courier_id)
        
        return request.app.state.templates.TemplateResponse(
        "operator_courier_view.html",
        {
            "request": request,
            "courier_name": courier_info["full_name"],
            "courier_id": courier_id,
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
            SELECT to_char(a.changed_at, 'DD-MM-YYYY HH24:MI') as changed_at, u.full_name as user_name, a.table_name, 
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
                   u.full_name as client_name, u.email as client_email, u.phone as client_phone,
                   s.status_name, cl.address as client_address
            FROM orders o
            JOIN clients cl ON o.client_id = cl.client_id
            JOIN users u ON cl.user_id = u.user_id
            JOIN statuses s ON o.status_id = s.status_id
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
            SELECT d.delivery_id, u.full_name as courier_name,
                l.latitude as delivery_lat, l.longitude as delivery_lng,
                dc.latitude, dc.longitude, dc.updated_at as coords_updated_at
            FROM deliveries d
            LEFT JOIN couriers co ON d.courier_id = co.courier_id
            LEFT JOIN users u ON co.user_id = u.user_id
            LEFT JOIN locations l ON d.location_id = l.location_id
            LEFT JOIN delivery_coordinates dc ON d.delivery_id = dc.delivery_id
            WHERE d.order_id = $1
        """, order_id)

    return request.app.state.templates.TemplateResponse(
        "order_detail.html",
        {
            "request": request,
            "order": dict(order),
            "items": [dict(i) for i in items],
            "delivery": dict(delivery) if delivery else None
        }
    )