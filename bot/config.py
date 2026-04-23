import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

DB_CONFIG = {
    "user"        : os.getenv("DB_USER", "postgres"),
    "password"    : os.getenv("DB_PASSWORD", ""),
    "database"    : os.getenv("DB_NAME", "logitrack"),
    "host"        : os.getenv("DB_HOST", "localhost"),
    "port"        : int(os.getenv("DB_PORT", 5432))
}

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:9092")
KAFKA_COORD_TOPIC = os.getenv("KAFKA_COORDINATES_TOPIC", "courier.coordinates")

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

# tables
ALLOWED_TABLES = ["users", "roles", "delivery_coordinates"]

TABLE_SCHEMA = {
    "users": {
        "read": ["first_name", 'last_name', "email", "phone"],
        "write": ["first_name",'last_name', "email", "phone", "password_hash"]  # password будет автоматически захеширован в боте
    },
    "roles": {
        "read": ["role_id", "role_name", "description"]
    },
    "delivery_coordinates": {
        "read": ["delivery_id"],
        "write": ["latitude", "longitude"]
    }
}