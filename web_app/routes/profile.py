# routes/profile.py
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from datetime import datetime
import re

from core.db import get_pool
from config import ROLE_NAMES

router = APIRouter()

# Валидация формата +7-(999)-999-99-99
PHONE_VALIDATION_REGEX = re.compile(r"^\+7-\(\d{3}\)-\d{3}-\d{2}-\d{2}$")

@router.get("/profile")
async def profile_page(request: Request):
    """Страница профиля — доступна всем авторизованным."""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=303)
    
    pool = get_pool(request)
    if not pool:
        return request.app.state.templates.TemplateResponse(
            "profile.html",
            {"request": request, "page_title": "Обо мне", "error": "БД недоступна"}
        )
    
    # Загружаем данные пользователя
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT u.first_name, u.last_name, u.email, u.phone, u.role_id,
                   c.address, c.date_of_birth, c.sex
            FROM users u
            LEFT JOIN clients c ON u.user_id = c.user_id
            WHERE u.user_id = $1
        """, user_id)
    
    if not row:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Форматируем дату для input type="date"
    dob = row["date_of_birth"]
    dob_str = dob.strftime("%Y-%m-%d") if dob else ""
    
    return request.app.state.templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "page_title": "Обо мне",
            "user": {
                "first_name"    : row["first_name"],
                "last_name"     : row["last_name"],
                "email"         : row["email"],
                "phone"         : row["phone"] or "",
                "role_id"       : row["role_id"],
                "role_name"     : ROLE_NAMES.get(row["role_id"], "Неизвестная роль"),
                "address"       : row["address"] or "",
                "date_of_birth" : dob_str,
                "sex"           : row["sex"] or "male"
            }
        }
    )

@router.post("/profile/update")
async def profile_update(
    request: Request,
    address: str = Form(...),
    latitude: str = Form(None),   # поле из виджета DaData
    longitude: str = Form(None),  # поле из виджета DaData
    date_of_birth: datetime = Form(None),
    sex: str = Form("male"),
    phone: str = Form(None)
):
    """Обновление профиля клиента: адрес + координаты из DaData."""
    user_id = request.session.get("user_id")
    role_id = request.session.get("role_id")
    
    if not user_id or role_id != 4:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    pool = get_pool(request)
    if not pool:
        request.session.setdefault("_messages", []).append("error: БД недоступна")
        return RedirectResponse("/profile", status_code=303)
    
    try:
        async with pool.acquire() as conn:
            # 1. Обновляем телефон в users
            if phone:
                clean = re.sub(r'\D', '', phone)
                if clean.startswith('8'): clean = '7' + clean[1:]
                if not clean.startswith('7'): clean = '7' + clean
                clean = clean[:11] # Обрезаем лишнее

                if len(clean) == 11 and clean.isdigit():
                    # Форматируем обратно под шаблон БД
                    phone = f"+7-({clean[1:4]})-{clean[4:7]}-{clean[7:9]}-{clean[9:11]}"
                else:
                    request.session.setdefault("_messages", []).append("error: Неверный формат телефона (требуется 11 цифр)")
                    return RedirectResponse("/profile", status_code=303)

                await conn.execute(
                    "UPDATE users SET phone = $1, updated_at = CURRENT_TIMESTAMP WHERE user_id = $2",
                    phone, user_id
                )
            
            # 2. Находим или создаём запись в locations
            lat = float(latitude) if latitude else None
            lng = float(longitude) if longitude else None
            
            loc_type_id = await conn.fetchval(
                "SELECT location_type_id FROM location_types WHERE location_type = 'delivery_point' LIMIT 1"
            )
            if not loc_type_id:
                raise RuntimeError("Тип локации 'delivery_point' не найден")

            location_id = None
            if lat is not None and lng is not None:
                # Ищем существующую локацию по строке адреса
                location_id = await conn.fetchval(
                    "SELECT location_id FROM locations WHERE address = $1 LIMIT 1",
                    address
                )
            
            if location_id is None:
                # Создаём новую локацию (координаты могут быть NULL при ручном вводе)
                row = await conn.fetchrow("""
                    INSERT INTO locations (location_type_id, address, latitude, longitude)
                    VALUES ($1, $2, $3, $4) RETURNING location_id
                """, loc_type_id, address, lat, lng)
                location_id = row["location_id"]
            
            # 3. Обновляем или создаём запись клиента
            exists = await conn.fetchval("SELECT 1 FROM clients WHERE user_id = $1", user_id)
            
            if exists:
                await conn.execute("""
                    UPDATE clients 
                    SET address = $1, date_of_birth = $2, sex = $3
                    WHERE user_id = $4
                """, address, date_of_birth or None, sex, user_id)
            else:
                await conn.execute("""
                    INSERT INTO clients (user_id, address, date_of_birth, sex)
                    VALUES ($1, $2, $3, $4)
                """, user_id, address, date_of_birth or None, sex)
        
        request.session.setdefault("_messages", []).append("success: Профиль обновлён")
        
    except Exception as e:
        request.session.setdefault("_messages", []).append(f"error: Ошибка обновления: {e}")
    
    return RedirectResponse("/profile", status_code=303)