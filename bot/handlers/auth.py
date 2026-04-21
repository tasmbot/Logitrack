# handlers/auth.py
import logging
import asyncpg
from telegram import Update
from telegram.ext import ContextTypes
from utils.helpers import delete_user_input
from core.context import FlowManager
from core.security import hash_password, verify_password, is_valid_bcrypt_length
from core.db import get_pool, verify_user_login, register_user
from utils.keyboards import kb_back, kb_auth_menu, kb_main_menu, kb_auth_fail

logger = logging.getLogger(__name__)

async def handle_login_email(update: Update, context: ContextTypes.DEFAULT_TYPE, email: str):
    await delete_user_input(update)
    FlowManager.set_temp_value(context, "temp_email", email)
    FlowManager.set_flow(context, "login_pass")
    await update.message.reply_text("🔑 Введите *пароль*:", parse_mode="Markdown", reply_markup=kb_back())

async def handle_login_pass(update: Update, context: ContextTypes.DEFAULT_TYPE, password: str):
    """Обработка ввода пароля при входе."""
    await delete_user_input(update)
    state = FlowManager.get(context)
    email = state.get("temp_email")
    pool = get_pool(context)
    
    if not pool:
        await update.message.reply_text("❌ БД недоступна.", reply_markup=kb_auth_menu())
        return
    if not is_valid_bcrypt_length(password):
        await update.message.reply_text("⚠️ Пароль слишком длинный (макс. 72 байта).", reply_markup=kb_auth_menu())
        return

    try:
        # один запрос получает всё: пароль, роль, данные курьера
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT u.user_id, u.role_id, u.password_hash,
                       c.courier_id, c.active,
                       CONCAT(u.first_name, ' ', u.last_name) as courier_name
                FROM users u
                LEFT JOIN couriers c ON u.user_id = c.user_id
                WHERE u.email = $1
            """, email)

        # Проверка пароля
        if not row or not verify_password(password, row["password_hash"]):
            FlowManager.set_flow(context, "auth_failed")
            await update.message.reply_text("❌ Неверная почта или пароль.", reply_markup=kb_auth_fail())
            return

        # Проверка роли
        if row["role_id"] != 3:
            await update.message.reply_text("⚠️ Доступ разрешён только курьерам.", reply_markup=kb_auth_menu())
            return

        # Проверка активации курьера
        if not row["active"] or row["courier_id"] is None:
            await update.message.reply_text("⚠️ Ваш аккаунт не активирован как курьер.", reply_markup=kb_auth_menu())
            return

        # Успешный вход
        FlowManager.set_authenticated(context, True)
        FlowManager.set_courier_data(context, row["user_id"], row["courier_id"], row["role_id"])
        FlowManager.set_flow(context, None)
        FlowManager.clear_temp_data(context)
        
        await update.message.reply_text(
            f"✅ *Вход выполнен!* Добро пожаловать, {row['courier_name']}.",
            parse_mode="Markdown",
            reply_markup=kb_main_menu()
        )
        
    except Exception as e:
        logger.error(f"Login error for {email}: {e}")
        await update.message.reply_text("❌ Ошибка авторизации. Попробуйте позже.", reply_markup=kb_auth_menu())
        
        
async def handle_reg_email(update: Update, context: ContextTypes.DEFAULT_TYPE, email: str):
    await delete_user_input(update)
    FlowManager.set_temp_value(context, "temp_email", email)
    FlowManager.set_flow(context, "reg_fullname")
    await update.message.reply_text("📛 Введите ваше *полное имя*:", parse_mode="Markdown", reply_markup=kb_back())

async def handle_reg_fullname(update: Update, context: ContextTypes.DEFAULT_TYPE, full_name: str):
    await delete_user_input(update)
    # Разбиваем имя на first/last если нужно, или сохраняем как first_name
    FlowManager.set_temp_value(context, "temp_first_name", full_name)
    FlowManager.set_temp_value(context, "temp_last_name", "")
    FlowManager.set_flow(context, "reg_phone")
    await update.message.reply_text("📞 Введите *номер телефона*:", parse_mode="Markdown", reply_markup=kb_back())

async def handle_reg_phone(update: Update, context: ContextTypes.DEFAULT_TYPE, phone: str):
    await delete_user_input(update)
    FlowManager.set_temp_value(context, "temp_phone", phone)
    FlowManager.set_flow(context, "reg_pass")
    await update.message.reply_text("🔑 Придумайте *пароль*:", parse_mode="Markdown", reply_markup=kb_back())

async def handle_reg_pass(update: Update, context: ContextTypes.DEFAULT_TYPE, password: str):
    await delete_user_input(update)
    state = FlowManager.get(context)
    pool = get_pool(context)
    if not pool:
        await update.message.reply_text("❌ БД недоступна.", reply_markup=kb_auth_menu())
        return
    if not is_valid_bcrypt_length(password):
        await update.message.reply_text("⚠️ Пароль слишком длинный.", reply_markup=kb_back())
        return

    try:
        await register_user(
            pool, 
            email=state["temp_email"], 
            first_name=state["temp_first_name"], 
            last_name=state["temp_last_name"],
            phone=state["temp_phone"], 
            password_hash=hash_password(password), 
            role_id=3
        )
        FlowManager.set_authenticated(context, True)
        FlowManager.set_flow(context, None)
        FlowManager.clear_temp_data(context)
        await update.message.reply_text(f"✅ Аккаунт создан! Добро пожаловать.", reply_markup=kb_main_menu())
    except asyncpg.UniqueViolationError:
        await update.message.reply_text("⚠️ Этот email уже зарегистрирован.", reply_markup=kb_auth_menu())
    except Exception as e:
        logger.error(f"Registration error: {e}")
        await update.message.reply_text(f"❌ Ошибка регистрации: {e}", reply_markup=kb_auth_menu())