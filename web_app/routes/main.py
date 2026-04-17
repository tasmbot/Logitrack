# routes/main.py
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import RedirectResponse, JSONResponse
from core.db import get_pool

# Константы ролей
ROLE_CLIENT = 4
ROLE_OPERATOR = 2
ROLE_COURIER = 3

router = APIRouter()

@router.get("/")
async def root(request: Request):
    """Перенаправление на дашборд или логин."""
    user_id = request.session.get("user_id")
    role = request.session.get("role_id")
    
    if not user_id:
        return RedirectResponse("/login", status_code=303)
    
    # Маршрутизация по роли
    if role == ROLE_CLIENT:
        return RedirectResponse("/dashboard/client", status_code=303)
    elif role == ROLE_OPERATOR:
        return RedirectResponse("/dashboard/operator", status_code=303)
    elif role == ROLE_COURIER:
        return RedirectResponse("/dashboard/courier", status_code=303)
    
    # Если роль неизвестна — на логин
    return RedirectResponse("/login", status_code=303)

@router.get("/dashboard/client")
async def client_dashboard(request: Request):
    """Дашборд клиента."""
    # 🔐 Прямая проверка роли
    if request.session.get("role_id") != ROLE_CLIENT:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    return request.app.state.templates.TemplateResponse(
        "client_dashboard.html", 
        {"request": request, "page_title": "Мои заказы"}
    )

@router.get("/dashboard/operator")
async def operator_dashboard(request: Request):
    """Дашборд оператора."""
    if request.session.get("role_id") != ROLE_OPERATOR:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    return request.app.state.templates.TemplateResponse(
        "operator_dashboard.html", 
        {"request": request, "page_title": "Панель оператора"}
    )

@router.get("/dashboard/courier")
async def courier_dashboard(request: Request):
    """Дашборд курьера."""
    if request.session.get("role_id") != ROLE_COURIER:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    return request.app.state.templates.TemplateResponse(
        "courier_dashboard.html", 
        {"request": request, "page_title": "Мои доставки"}
    )

# 👇 Заглушка API для статистики (будет наполнена на Этапе 3)
@router.get("/api/stats/{role}")
async def get_stats(request: Request, role: str):
    """Проверка доступа к API + заглушка данных."""
    allowed = {
        "client": [ROLE_CLIENT],
        "operator": [ROLE_OPERATOR], 
        "courier": [ROLE_COURIER]
    }
    user_role = request.session.get("role_id")
    
    if role not in allowed or user_role not in allowed[role]:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    # Возвращаем пустые данные (заполним позже)
    return {
        "active_orders": 0,
        "delivered_today": 0,
        "avg_delivery_time": "00:00",
        "chart_data": {"labels": [], "datasets": []}
    }

@router.get("/courier/api/orders")
async def get_courier_orders(request: Request):
    """Возвращает заказы, назначенные текущему курьеру."""
    if request.session.get("role_id") != 3:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
        
    user_id = request.session.get("user_id")
    pool = get_pool(request)
    if not pool:
        return JSONResponse(content=[])

    async with pool.acquire() as conn:
        # 1. Получаем courier_id по user_id
        courier_row = await conn.fetchrow("SELECT courier_id FROM couriers WHERE user_id = $1", user_id)
        if not courier_row:
            return JSONResponse(content=[])
        courier_id = courier_row["courier_id"]

        # 2. Загружаем заказы курьера
        rows = await conn.fetch("""
            SELECT 
                o.order_id,
                CONCAT(u.first_name, ' ', u.last_name) AS client_name,
                u.phone AS client_phone,
                l.address AS delivery_address,
                COALESCE(o.total_weight, 0) AS total_weight,
                s.status_name,
                to_char(o.created_at, 'DD-MM-YYYY HH24:MI') as created_at
            FROM deliveries d
            JOIN orders o ON d.order_id = o.order_id
            JOIN statuses s ON o.status_id = s.status_id
            JOIN clients c ON o.client_id = c.client_id
            JOIN users u ON c.user_id = u.user_id
            LEFT JOIN locations l ON d.location_id = l.location_id
            WHERE d.courier_id = $1
            ORDER BY o.created_at DESC
        """, courier_id)
        
    return [dict(r) for r in rows]

@router.get("/courier/api/route")
async def get_courier_route(request: Request):
    """Возвращает точки маршрута для текущего курьера."""
    if request.session.get("role_id") != 3:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
        
    user_id = request.session.get("user_id")
    pool = get_pool(request)
    if not pool:
        return JSONResponse(content=[])

    async with pool.acquire() as conn:
        # 1. Получаем courier_id
        courier = await conn.fetchrow("SELECT courier_id FROM couriers WHERE user_id = $1", user_id)
        if not courier:
            return JSONResponse(content=[])

        # 2. Находим активный маршрут курьера
        delivery = await conn.fetchrow("""
            SELECT route_id FROM deliveries
            WHERE courier_id = $1 AND actual_delivery_datetime IS NULL
            ORDER BY updated_at DESC LIMIT 1
        """, courier["courier_id"])

        if not delivery or not delivery["route_id"]:
            return JSONResponse(content=[])

        # 3. Загружаем точки маршрута
        points = await conn.fetch("""
            SELECT 
                rp.sequence_num,
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

    return [dict(p) for p in points]