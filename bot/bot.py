import logging
import asyncpg
from passlib.context import CryptContext
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

from config import BOT_TOKEN, DB_CONFIG, ALLOWED_TABLES, TABLE_SCHEMA

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ─── Утилиты клавиатур ──────────────────────────────────────────────────────
def kb_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="menu:main")]])

def kb_auth_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔐 Войти / Регистрация", callback_data="auth:start")]])

def kb_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Прочитать таблицу", callback_data="db:read")],
        [InlineKeyboardButton("📝 Записать в таблицу", callback_data="db:write")],
        [InlineKeyboardButton("🚪 Выйти", callback_data="auth:logout")]
    ])

def kb_tables(action: str) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(t, callback_data=f"db:select:{action}:{t}")] for t in ALLOWED_TABLES]
    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)

def kb_auth_fail() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Повторить вход", callback_data="auth:start")],
        [InlineKeyboardButton("✅ Зарегистрироваться", callback_data="auth:reg")],
        [InlineKeyboardButton("🔙 Назад", callback_data="menu:start")]
    ])

# ─── Управление БД ──────────────────────────────────────────────────────────
async def setup_db(application):
    try:
        pool = await asyncpg.create_pool(**DB_CONFIG, min_size=1, max_size=5)
        application.bot_data["db_pool"] = pool
        
        # Автоматически создаём таблицу авторизации, если её нет
        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Для демо создаём остальные таблицы, если их нет
            for t in ALLOWED_TABLES:
                await conn.execute(f"CREATE TABLE IF NOT EXISTS {t} (id SERIAL PRIMARY KEY, name TEXT, value TEXT)")
                
        logging.info("✅ Подключение к PostgreSQL и проверка таблиц успешны")
    except Exception as e:
        logging.error(f"❌ Ошибка инициализации БД: {e}")
        application.bot_data["db_pool"] = None

async def close_db(application):
    pool = application.bot_data.get("db_pool")
    if pool:
        await pool.close()
        logging.info("🔌 Соединение с PostgreSQL закрыто")

# ─── Обработчики команд ─────────────────────────────────────────────────────
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Сброс состояния при /start
    context.user_data.clear()
    
    text = (
        "🤖 *Привет! Я универсальный Telegram-бот.*\n\n"
        "🔹 `Эхо-режим`: повторяю ваши сообщения\n"
        "🔹 `БД`: читаю и записываю данные в PostgreSQL\n"
        "🔹 `Навигация`: всё управление через кнопки\n\n"
        "Для доступа к функциям БД необходимо авторизоваться."
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb_auth_menu())

# ─── Обработчики кнопок (Callback) ──────────────────────────────────────────
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split(":")  # Убрали ограничение на 2 части
    action = parts[0]

    # Навигация
    if query.data == "menu:start":
        await start_cmd(update, context)
        return
    elif query.data == "menu:main":
        if context.user_data.get("auth"):
            await query.edit_message_text("📂 *Главное меню*", parse_mode="Markdown", reply_markup=kb_main_menu())
        else:
            await query.edit_message_text("⚠️ Требуется авторизация.", reply_markup=kb_auth_menu())
        return

    # Авторизация
    elif action == "auth":
        target = parts[1]
        if target == "start":
            context.user_data["flow"] = "login_email"
            await query.edit_message_text("🔑 Введите вашу *почту*:", parse_mode="Markdown", reply_markup=kb_back())
        elif target == "reg":
            context.user_data["flow"] = "reg_email"
            await query.edit_message_text("📝 Регистрация. Введите *почту*:", parse_mode="Markdown", reply_markup=kb_back())
        elif target == "logout":
            context.user_data.clear()
            await query.edit_message_text("👋 Вы вышли из системы.", reply_markup=kb_auth_menu())
        return

    # Работа с БД
    elif action == "db":
        sub_action = parts[1]
        
        if sub_action == "read":
            await query.edit_message_text("📖 Выберите таблицу для чтения:", reply_markup=kb_tables("read"))
            return
        elif sub_action == "write":
            await query.edit_message_text("📝 Выберите таблицу для записи:", reply_markup=kb_tables("write"))
            return
        elif sub_action == "select":
            mode = parts[2]
            table = parts[3]
            
            schema = TABLE_SCHEMA.get(table)
            if not schema:
                await query.edit_message_text("⚠️ Таблица не сконфигурирована.", reply_markup=kb_back())
                return

            pool = context.bot_data.get("db_pool")
            if not pool:
                await query.edit_message_text("❌ Нет подключения к БД.", reply_markup=kb_back())
                return

            if mode == "read":
                cols = schema["read"]
                cols_str = ", ".join(f'"{c}"' for c in cols)  # Кавычки для безопасности
                async with pool.acquire() as conn:
                    row = await conn.fetchrow(f"SELECT {cols_str} FROM {table} LIMIT 1")
                if not row:
                    await query.edit_message_text(f"📭 В таблице `{table}` нет записей.", reply_markup=kb_back())
                    return
                text = f"📊 Данные из *{table}*:\n" + "─" * 30 + "\n" + "\n".join(f"• `{k}`: `{v}`" for k, v in row.items())
                await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb_back())
                
            else:  # mode == "write"
                context.user_data["target_table"] = table
                context.user_data["target_cols"] = schema["write"]  # Берём только нужные для записи
                context.user_data["flow"] = "write_data"
                template = "\n".join([f"{c}: <значение>" for c in schema["write"]])
                msg = f"✅ Таблица `{table}`.\nВведите данные в формате:\n```\n{template}\n```"
                await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=kb_back())
            return

    # Fallback
    await query.edit_message_text("⚠️ Действие недоступно.", reply_markup=kb_back())

# ─── Центральный обработчик текста (State Machine) ──────────────────────────
async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    flow = context.user_data.get("flow")
    pool = context.bot_data.get("db_pool")

    # ── 1. Авторизация: Email ──
    if flow == "login_email":
        context.user_data["temp_email"] = text
        context.user_data["flow"] = "login_pass"
        await update.message.reply_text("🔑 Введите *пароль*:", parse_mode="Markdown", reply_markup=kb_back())
        return

    # ── 2. Авторизация: Password ──
    if flow == "login_pass":
        email = context.user_data.get("temp_email")
        if not pool:
            await update.message.reply_text("❌ БД недоступна.", reply_markup=kb_auth_menu())
            return

        if len(text.encode("utf-8")) > 72:
            await update.message.reply_text("⚠️ Пароль слишком длинный (макс. 72 байта). Введите короче.", reply_markup=kb_auth_menu())
            return

        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT password_hash FROM users WHERE email = $1", email)

        is_valid = False
        if row and row["password_hash"]:
            try:
                is_valid = pwd_context.verify(text, row["password_hash"])
            except (ValueError, Exception):
                await update.message.reply_text("⚠️ Ошибка формата хеша. Зарегистрируйтесь заново.", reply_markup=kb_auth_fail())
                return

        if is_valid:
            context.user_data["auth"] = True
            context.user_data["flow"] = None
            await update.message.reply_text("✅ *Вход выполнен!* Добро пожаловать.", parse_mode="Markdown", reply_markup=kb_main_menu())
        else:
            context.user_data["flow"] = "auth_failed"
            await update.message.reply_text("❌ Неверная почта или пароль.", reply_markup=kb_auth_fail())
        return

    # ── 3. Регистрация: Пошаговый сбор ──
    if flow == "reg_email":
        context.user_data["temp_email"] = text
        context.user_data["flow"] = "reg_fullname"
        await update.message.reply_text("📛 Введите ваше *полное имя*:", parse_mode="Markdown", reply_markup=kb_back())
        return

    if flow == "reg_fullname":
        context.user_data["temp_full_name"] = text
        context.user_data["flow"] = "reg_phone"
        await update.message.reply_text("📞 Введите *номер телефона*:", parse_mode="Markdown", reply_markup=kb_back())
        return

    if flow == "reg_phone":
        context.user_data["temp_phone"] = text
        context.user_data["flow"] = "reg_pass"
        await update.message.reply_text("🔑 Придумайте *пароль*:", parse_mode="Markdown", reply_markup=kb_back())
        return

    if flow == "reg_pass":
        email = context.user_data.get("temp_email")
        full_name = context.user_data.get("temp_full_name")
        phone = context.user_data.get("temp_phone")

        if not pool:
            await update.message.reply_text("❌ БД недоступна.", reply_markup=kb_auth_menu())
            return

        if len(text.encode("utf-8")) > 72:
            await update.message.reply_text("⚠️ Пароль слишком длинный (макс. 72 байта).", reply_markup=kb_back())
            return

        try:
            hashed = pwd_context.hash(text)
            async with pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO users (email, full_name, phone, password_hash, role_id) VALUES ($1, $2, $3, $4, $5)",
                    email, full_name, phone, hashed, 4 # роль "Клиент" по умолчанию
                )
            context.user_data["auth"] = True
            context.user_data["flow"] = None
            for k in ("temp_email", "temp_full_name", "temp_phone"):
                context.user_data.pop(k, None)
            await update.message.reply_text(f"✅ Аккаунт `{email}` создан! Добро пожаловать.", reply_markup=kb_main_menu())
        except asyncpg.UniqueViolationError:
            await update.message.reply_text("⚠️ Этот email уже зарегистрирован.", reply_markup=kb_auth_menu())
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка регистрации: {e}", reply_markup=kb_auth_menu())
        return

    # ── 4. Запись в БД: Данные ──
    if flow == "write_data":
        table = context.user_data.get("target_table")
        cols = context.user_data.get("target_cols", [])
        
        if not table or not cols or not pool:
            await update.message.reply_text("⚠️ Ошибка состояния. Начните заново: /cancel", reply_markup=kb_main_menu())
            context.user_data["flow"] = None
            return

        # Парсинг `ключ: значение`
        parsed = {}
        for line in text.split("\n"):
            if ":" in line:
                key, val = line.split(":", 1)
                parsed[key.strip()] = val.strip()

        # Авто-хеширование пароля, если поле есть в схеме
        if "password" in parsed:
            parsed["password"] = pwd_context.hash(parsed["password"])

        # Валидация обязательных колонок
        missing = [c for c in cols if c not in parsed]
        if missing:
            await update.message.reply_text(
                f"❌ Отсутствуют колонки:\n`{', '.join(missing)}`\nПроверьте формат и отправьте снова.",
                parse_mode="Markdown"
            )
            return

        ordered_cols = [c for c in cols if c in parsed]
        col_names = ", ".join(ordered_cols)
        placeholders = ", ".join([f"${i+1}" for i in range(len(ordered_cols))])
        values = [parsed[c] for c in ordered_cols]
        query = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) RETURNING *;"

        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(query, *values)

            res = f"✅ Строка успешно вставлена в *{table}*!\n" + "─" * 30 + "\n"
            res += "\n".join(f"• `{k}`: `{v}`" for k, v in row.items())
            await update.message.reply_text(res, parse_mode="Markdown", reply_markup=kb_back())

            # Успешно → сбрасываем состояние ввода
            context.user_data.pop("flow", None)
            context.user_data.pop("target_table", None)
            context.user_data.pop("target_cols", None)
        except asyncpg.DataError as de:
            await update.message.reply_text(f"❌ Ошибка типа данных: {de}\n💡 Проверьте соответствие типов колонок.")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка вставки: {e}")
        return

    # ── 5. Fallback: Эхо-режим ──
    await update.message.reply_text(update.message.text)

# ─── Запуск ─────────────────────────────────────────────────────────────────
def main() -> None:
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.post_init = setup_db
    app.post_shutdown = close_db

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("cancel", start_cmd))  # Сброс и возврат в начало
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

    print("✅ Бот запущен.")
    print("   • /start — приветствие и меню")
    print("   • /cancel — сброс состояния")
    app.run_polling()

if __name__ == '__main__':
    main()