# handlers/auth.py
"""Обработчики авторизации и регистрации."""
import logging
from telegram import Update
from telegram.ext import ContextTypes

from utils.helpers import delete_user_input
from core.context import FlowManager
from core.security import hash_password, verify_password, is_valid_bcrypt_length
from core.db import get_pool, get_courier_info
from utils.keyboards import kb_back, kb_auth_menu, kb_main_menu, kb_auth_fail

logger = logging.getLogger(__name__)


async def handle_login_email(update: Update, context: ContextTypes.DEFAULT_TYPE, email: str):
    """Обработка ввода email при входе."""
    await delete_user_input(update)  # ← Удаляем письмо из чата
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
        await update.message.reply_text(
            "⚠️ Пароль слишком длинный (макс. 72 байта). Введите короче.",
            reply_markup=kb_auth_menu()
        )
        return

    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT password_hash FROM users WHERE email = $1",
                email
            )
        
        if row and verify_password(password, row["password_hash"]):
            # 👇 Получаем user_id из БД (предполагаем, что он есть в запросе)
            async with pool.acquire() as conn:
                user_row = await conn.fetchrow(
                    "SELECT user_id, role_id FROM users WHERE email = $1",
                    email
                )
            
            if not user_row:
                await update.message.reply_text("❌ Ошибка авторизации.", reply_markup=kb_auth_menu())
                return
            
            user_id = user_row["user_id"]
            role_id = user_row["role_id"]
            
            # 👇 Проверяем, что это курьер
            if role_id != 3:
                await update.message.reply_text(
                    "⚠️ Доступ разрешён только курьерам (роль «Курьер»).",
                    reply_markup=kb_auth_menu()
                )
                return
            
            # 👇 Получаем courier_id
            courier_info = await get_courier_info(pool, user_id)
            if not courier_info or not courier_info["is_active_courier"]:
                await update.message.reply_text(
                    "⚠️ Ваш аккаунт не активирован как курьер. Обратитесь к администратору.",
                    reply_markup=kb_auth_menu()
                )
                return
            
            # 👇 Сохраняем данные в контексте
            FlowManager.set_authenticated(context, True)
            FlowManager.set_courier_data(context, user_id, courier_info["courier_id"], role_id)
            FlowManager.set_flow(context, None)
            FlowManager.clear_temp_data(context)
            
            await update.message.reply_text(
                f"✅ *Вход выполнен!* Добро пожаловать, курьер #{courier_info['courier_id']}.",
                parse_mode="Markdown",
                reply_markup=kb_main_menu()
            )
        else:
            FlowManager.set_flow(context, "auth_failed")
            await update.message.reply_text(
                "❌ Неверная почта или пароль.",
                reply_markup=kb_auth_fail()
            )
    except Exception as e:
        logger.error(f"Login error for {email}: {e}")
        await update.message.reply_text(
            "❌ Ошибка авторизации. Попробуйте позже.",
            reply_markup=kb_auth_menu()
        )


async def handle_reg_email(update: Update, context: ContextTypes.DEFAULT_TYPE, email: str):
    """Обработка ввода email при регистрации."""
    await delete_user_input(update)
    FlowManager.set_temp_value(context, "temp_email", email)
    FlowManager.set_flow(context, "reg_fullname")
    await update.message.reply_text(
        "📛 Введите ваше *полное имя*:",
        parse_mode="Markdown",
        reply_markup=kb_back()
    )


async def handle_reg_fullname(update: Update, context: ContextTypes.DEFAULT_TYPE, full_name: str):
    """Обработка ввода полного имени при регистрации."""
    await delete_user_input(update)
    FlowManager.set_temp_value(context, "temp_full_name", full_name)
    FlowManager.set_flow(context, "reg_phone")
    await update.message.reply_text(
        "📞 Введите *номер телефона*:",
        parse_mode="Markdown",
        reply_markup=kb_back()
    )


async def handle_reg_phone(update: Update, context: ContextTypes.DEFAULT_TYPE, phone: str):
    """Обработка ввода телефона при регистрации."""
    await delete_user_input(update)
    FlowManager.set_temp_value(context, "temp_phone", phone)
    FlowManager.set_flow(context, "reg_pass")
    await update.message.reply_text(
        "🔑 Придумайте *пароль*:",
        parse_mode="Markdown",
        reply_markup=kb_back()
    )


async def handle_reg_pass(update: Update, context: ContextTypes.DEFAULT_TYPE, password: str):
    """Обработка ввода пароля при регистрации и создание аккаунта."""
    await delete_user_input(update)
    state = FlowManager.get(context)
    email = state.get("temp_email")
    full_name = state.get("temp_full_name")
    phone = state.get("temp_phone")
    pool = get_pool(context)
    
    if not pool:
        await update.message.reply_text("❌ БД недоступна.", reply_markup=kb_auth_menu())
        return

    if not is_valid_bcrypt_length(password):
        await update.message.reply_text(
            "⚠️ Пароль слишком длинный (макс. 72 байта).",
            reply_markup=kb_back()
        )
        return

    try:
        hashed = hash_password(password)
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO users (email, full_name, phone, password_hash, role_id)
                VALUES ($1, $2, $3, $4, $5)
                """,
                email, full_name, phone, hashed, 3  # role_id=3 → "Курьер"
            )
        
        FlowManager.set_authenticated(context, True)
        FlowManager.set_flow(context, None)
        FlowManager.clear_temp_data(context)
        
        await update.message.reply_text(
            f"✅ Аккаунт `{email}` создан! Добро пожаловать.",
            reply_markup=kb_main_menu()
        )
        
    except Exception as e:
        logger.error(f"Registration error: {e}")
        if "unique constraint" in str(e).lower() or "23505" in str(e):
            await update.message.reply_text(
                "⚠️ Этот email уже зарегистрирован.",
                reply_markup=kb_auth_menu()
            )
        else:
            await update.message.reply_text(
                f"❌ Ошибка регистрации: {e}",
                reply_markup=kb_auth_menu()
            )