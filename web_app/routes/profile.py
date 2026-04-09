# routes/profile.py
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from core.db import get_pool
from config import ROLE_NAMES

from datetime import datetime

router = APIRouter()

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
            SELECT u.full_name, u.email, u.phone, u.role_id,
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
                "full_name": row["full_name"],
                "email": row["email"],
                "phone": row["phone"] or "",
                "role_id": row["role_id"],
                "role_name": ROLE_NAMES.get(row["role_id"], "Неизвестная роль"),
                "address": row["address"] or "",
                "date_of_birth": dob_str,
                "sex": row["sex"] or "male"
            }
        }
    )

@router.post("/profile/update")
async def profile_update(
    request: Request,
    address: str = Form(...),
    date_of_birth: datetime = Form(None),
    sex: str = Form("male"),
    phone: str = Form(None)
):
    """Обновление профиля — только для клиентов (для MVP)."""
    user_id = request.session.get("user_id")
    role_id = request.session.get("role_id")
    
    if not user_id or role_id != 4:  # Только клиенты могут редактировать профиль в MVP
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    pool = get_pool(request)
    if not pool:
        request.session.setdefault("_messages", []).append("error: БД недоступна")
        return RedirectResponse("/profile", status_code=303)
    
    try:
        async with pool.acquire() as conn:
            # Обновляем телефон в users (если передан)
            if phone:
                await conn.execute(
                    "UPDATE users SET phone = $1, updated_at = CURRENT_TIMESTAMP WHERE user_id = $2",
                    phone, user_id
                )
            
            # Обновляем/создаём запись в clients
            # Сначала проверяем, есть ли запись
            exists = await conn.fetchval(
                "SELECT 1 FROM clients WHERE client_id = (SELECT client_id FROM clients WHERE user_id = $1 LIMIT 1)",
                user_id
            )
            
            if exists:
                await conn.execute("""
                    UPDATE clients 
                    SET address = $1, date_of_birth = $2, sex = $3
                    WHERE user_id = $4
                """, address, date_of_birth or None, sex, user_id)
            else:
                # Создаём новую запись (упрощённо, без location_id для MVP)
                await conn.execute("""
                    INSERT INTO clients (user_id, address, date_of_birth, sex)
                    VALUES ($1, $2, $3, $4)
                """, user_id, address, date_of_birth or None, sex)
        
        request.session.setdefault("_messages", []).append("success: Профиль обновлён")
        
    except Exception as e:
        request.session.setdefault("_messages", []).append(f"error: Ошибка обновления: {e}")
    
    return RedirectResponse("/profile", status_code=303)