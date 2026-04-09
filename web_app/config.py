import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "fallback-dev-key")

DB_CONFIG = {
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "logitrack"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432))
}

# Маппинг role_id → читаемое название
ROLE_NAMES = {
    1: "Администратор",
    2: "Оператор",
    3: "Курьер",
    4: "Клиент"
}

# Вспомогательная функция для шаблонов
def get_role_name(role_id: int) -> str:
    return ROLE_NAMES.get(role_id, "Неизвестная роль")