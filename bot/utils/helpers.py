# utils/helpers.py
import logging
from telegram import Update

logger = logging.getLogger(__name__)

async def delete_user_input(update: Update) -> None:
    """
    Мгновенно удаляет сообщение пользователя из чата.
    Безопасно игнорирует ошибки, если сообщение уже удалено или недоступно.
    """
    try:
        if update.message:
            await update.message.delete()
    except Exception as e:
        logger.debug(f"Не удалось удалить сообщение пользователя: {e}")