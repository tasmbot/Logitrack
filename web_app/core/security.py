# core/security.py
"""Модуль безопасности: хеширование и проверка паролей."""
from passlib.context import CryptContext

# Инициализация контекста для работы с паролями
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """
    Хеширование пароля с использованием bcrypt.
    
    Args:
        plain_password: Исходный пароль в открытом виде.
        
    Returns:
        str: Хеш пароля в формате bcrypt ($2a$, $2b$ или $2y$).
    """
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Проверка соответствия пароля хешу.
    
    Args:
        plain_password: Пароль, введённый пользователем.
        hashed_password: Хеш из базы данных.
        
    Returns:
        bool: True если пароль верный, False в противном случае.
    """
    if not hashed_password or not plain_password:
        return False
    
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except (ValueError, Exception):
        # Ловим ошибки при некорректном формате хеша
        return False


def is_valid_bcrypt_length(password: str, max_bytes: int = 72) -> bool:
    """
    Проверка длины пароля в байтах (ограничение bcrypt).
    
    Args:
        password: Проверяемый пароль.
        max_bytes: Максимальная длина в байтах (по умолчанию 72).
        
    Returns:
        bool: True если длина в пределах лимита.
    """
    return len(password.encode("utf-8")) <= max_bytes