# handlers/db_write.py
"""Обработчики записи данных в базу."""
import logging
from telegram import CallbackQuery, Update
from telegram.ext import ContextTypes
from core.db import get_pool, insert_row
from core.security import hash_password
from utils.keyboards import kb_back

logger = logging.getLogger(__name__)


async def prepare_write_form(
    query: CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
    table_name: str,
    columns: list[str]
):
    """
    Подготовка формы для ввода данных перед записью.
    
    Args:
        query: Объект callback-запроса.
        context: Контекст приложения.
        table_name: Имя целевой таблицы.
        columns: Список колонок для заполнения.
    """
    # Сохраняем целевую таблицу в состоянии
    from core.context import FlowManager
    FlowManager.set_target_table(context, table_name, columns)
    FlowManager.set_flow(context, "write_data")
    
    # Формируем шаблон ввода
    template = "\n".join([f"{col}: <значение>" for col in columns])
    msg = (
        f"✅ Таблица `{table_name}`.\n"
        f"Введите данные в формате (каждая пара с новой строки):\n"
        f"```\n{template}\n```"
    )
    
    await query.edit_message_text(
        msg,
        parse_mode="Markdown",
        reply_markup=kb_back()
    )


async def handle_write_data(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """
    Обработка введённых данных и выполнение INSERT.
    
    Args:
        update: Объект обновления.
        context: Контекст приложения.
        text: Текст сообщения пользователя.
    """
    from core.context import FlowManager
    
    table, cols = FlowManager.get_target_table(context)
    pool = get_pool(context)
    
    if not table or not cols or not pool:
        await update.message.reply_text(
            "⚠️ Ошибка состояния. Начните заново: /cancel",
            reply_markup=kb_back()
        )
        FlowManager.set_flow(context, None)
        return
    
    # Парсинг ввода: "ключ: значение"
    parsed = {}
    for line in text.split("\n"):
        if ":" in line:
            key, val = line.split(":", 1)
            parsed[key.strip()] = val.strip()
    
    # Авто-хеширование поля password, если оно есть
    if "password" in parsed:
        parsed["password"] = hash_password(parsed["password"])
    
    # Валидация наличия всех обязательных колонок
    missing = [c for c in cols if c not in parsed]
    if missing:
        await update.message.reply_text(
            f"❌ Отсутствуют колонки:\n`{', '.join(missing)}`\n"
            f"Проверьте формат и отправьте данные снова.",
            parse_mode="Markdown"
        )
        return
    
    # Подготовка параметров запроса
    ordered_cols = [c for c in cols if c in parsed]
    values = [parsed[c] for c in ordered_cols]
    
    try:
        row = await insert_row(pool, table, ordered_cols, values)
        
        # Формирование ответа
        res = f"✅ Строка успешно вставлена в *{table}*!\n" + "─" * 30 + "\n"
        res += "\n".join(f"• `{k}`: `{v}`" for k, v in row.items())
        
        await update.message.reply_text(
            res,
            parse_mode="Markdown",
            reply_markup=kb_back()
        )
        
        # Успех → сброс состояния
        FlowManager.set_flow(context, None)
        FlowManager.clear_temp_data(context)
        
    except Exception as e:
        logger.error(f"Write error to {table}: {e}")
        error_msg = str(e).lower()
        
        if "null value" in error_msg or "23502" in str(e):
            await update.message.reply_text(
                "❌ Попробуйте указать значения для всех обязательных полей.",
                reply_markup=kb_back()
            )
        elif "unique constraint" in error_msg or "23505" in str(e):
            await update.message.reply_text(
                "⚠️ Такая запись уже существует (нарушение уникальности).",
                reply_markup=kb_back()
            )
        else:
            await update.message.reply_text(
                f"❌ Ошибка вставки: {e}",
                reply_markup=kb_back()
            )