# handlers/db_read.py
"""Обработчики чтения данных из базы."""
import logging
from telegram import CallbackQuery
from telegram.ext import ContextTypes
from core.db import get_pool, fetch_one_row
from utils.keyboards import kb_back

logger = logging.getLogger(__name__)


async def handle_read_table(
    query: CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
    table_name: str,
    columns: list[str]
):
    """
    Чтение первой строки из указанной таблицы.
    
    Args:
        query: Объект callback-запроса.
        context: Контекст приложения.
        table_name: Имя таблицы.
        columns: Список колонок для выборки.
    """
    pool = get_pool(context)
    if not pool:
        await query.edit_message_text(
            "❌ Нет подключения к БД.",
            reply_markup=kb_back()
        )
        return
    
    try:
        row = await fetch_one_row(pool, table_name, columns, limit=1)
        
        if not row:
            await query.edit_message_text(
                f"📭 В таблице `{table_name}` нет записей.",
                reply_markup=kb_back()
            )
            return
        
        # Формирование читаемого вывода
        text = f"📊 Данные из *{table_name}*:\n" + "─" * 30 + "\n"
        for col_name, col_value in row.items():
            text += f"• `{col_name}`: `{col_value}`\n"
        
        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=kb_back()
        )
        
    except Exception as e:
        logger.error(f"Read error from {table_name}: {e}")
        await query.edit_message_text(
            f"❌ Ошибка чтения: {e}",
            reply_markup=kb_back()
        )