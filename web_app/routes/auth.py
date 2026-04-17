# routes/auth.py
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from core.security import hash_password, verify_password
from core.db import get_pool
import re

# Константы ролей (дублируем для простоты MVP)
ROLE_CLIENT = 4
ROLE_OPERATOR = 2
ROLE_COURIER = 3

router = APIRouter()

@router.get("/login")
async def login_page(request: Request):
    """Страница входа."""
    return request.app.state.templates.TemplateResponse("login.html", {"request": request})

@router.post("/login")
async def login_submit(request: Request, email: str = Form(...), password: str = Form(...)):
    """Обработка формы входа."""
    pool = request.app.state.db_pool
    
    # Проверка подключения к БД
    if not pool:
        request.session.setdefault("_messages", []).append("error: БД недоступна")
        return RedirectResponse("/login", status_code=303)

    # Поиск пользователя
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT user_id, role_id, password_hash FROM users WHERE email = $1",
            email
        )

    # Проверка пароля
    if row and verify_password(password, row["password_hash"]):
        # Сохраняем сессию
        request.session["user_id"] = row["user_id"]
        request.session["role_id"] = row["role_id"]
        
        role = row["role_id"]
        if role == ROLE_CLIENT:
            return RedirectResponse("/dashboard/client", status_code=303)
        elif role == ROLE_OPERATOR:
            return RedirectResponse("/dashboard/operator", status_code=303)
        elif role == ROLE_COURIER:
            return RedirectResponse("/dashboard/courier", status_code=303)
        else:
            # Неизвестная роль → на логин
            request.session.clear()
            request.session.setdefault("_messages", []).append("error: Неизвестная роль")
            return RedirectResponse("/login", status_code=303)
    
    # Неверные данные
    request.session.setdefault("_messages", []).append("error: Неверный email или пароль")
    return RedirectResponse("/login", status_code=303)

@router.post("/logout")
async def logout(request: Request):
    """Выход из системы."""
    request.session.clear()
    return RedirectResponse("/login", status_code=303)

# === РЕГИСТРАЦИЯ ===
@router.get("/register")
async def register_page(request: Request):
    """Страница регистрации."""
    return request.app.state.templates.TemplateResponse("register.html", {"request": request})

@router.post("/register")
async def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    phone: str = Form(None),
    address: str = Form(None),
    date_of_birth: str = Form(None),
    sex: str = Form("male"),
    role: str = Form("client")
):
    """Обработка формы регистрации."""
    pool = get_pool(request)
    if not pool:
        request.session.setdefault("_messages", []).append("error: БД недоступна")
        return RedirectResponse("/register", status_code=303)

    # 1. Валидация
    if password != confirm_password:
        request.session.setdefault("_messages", []).append("error: Пароли не совпадают")
        return RedirectResponse("/register", status_code=303)
    
    if len(password) < 6:
        request.session.setdefault("_messages", []).append("error: Пароль должен содержать минимум 6 символов")
        return RedirectResponse("/register", status_code=303)

    if role not in ("client", "courier"):
        request.session.setdefault("_messages", []).append("error: Неверная роль")
        return RedirectResponse("/register", status_code=303)

    try:
        async with pool.acquire() as conn:
            # 2. Проверка уникальности email
            exists = await conn.fetchval("SELECT 1 FROM users WHERE email = $1", email)
            if exists:
                request.session.setdefault("_messages", []).append("error: Этот email уже зарегистрирован")
                return RedirectResponse("/register", status_code=303)

            # 3. Хеширование пароля
            pwd_hash = hash_password(password)
            role_id = 4 if role == "client" else 3

            # 4. Создание пользователя
            user = await conn.fetchrow("""
                INSERT INTO users (email, password_hash, first_name, last_name, phone, role_id)
                VALUES ($1, $2, $3, $4, $5, $6) RETURNING user_id
            """, email, pwd_hash, first_name, last_name, phone or None, role_id)
            
            user_id = user["user_id"]

            # 5. Создание записи в зависимости от роли
            if role == "client":
                await conn.execute("""
                    INSERT INTO clients (user_id, address, date_of_birth, sex)
                    VALUES ($1, $2, $3, $4)
                """, user_id, address or None, date_of_birth or None, sex)

        request.session.setdefault("_messages", []).append("success: Регистрация успешна! Теперь войдите в систему.")
        return RedirectResponse("/login", status_code=303)

    except Exception as e:
        request.session.setdefault("_messages", []).append(f"error: Ошибка регистрации: {str(e)}")
        return RedirectResponse("/register", status_code=303)