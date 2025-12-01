import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, Tuple

DB_PATH = Path("user.db")


@contextmanager
def get_db_connection():
    """Контекстный менеджер для безопасной работы с БД"""
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Инициализация базы данных"""
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                city TEXT,
                street TEXT,
                house TEXT
            )
        """)
        conn.commit()


def user_exists(user_id: int) -> bool:
    """Проверка существования пользователя"""
    with get_db_connection() as conn:
        result = conn.execute(
            "SELECT 1 FROM users WHERE user_id = ? LIMIT 1", (user_id,)
        ).fetchone()
        return result is not None


def get_user_address(user_id: int) -> Optional[Tuple[str, str, str]]:
    """Получение адреса пользователя"""
    with get_db_connection() as conn:
        result = conn.execute(
            "SELECT city, street, house FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return result


def add_user(user_id: int, username: str, city: str, street: str, house: str):
    """Добавление или обновление пользователя"""
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO users (user_id, username, city, street, house)
            VALUES (?, ?, ?, ?, ?)
        """,
            (user_id, username, city, street, house),
        )
        conn.commit()
