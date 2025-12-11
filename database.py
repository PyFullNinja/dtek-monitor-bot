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
    """Инициализация базы данных с миграциями"""
    with get_db_connection() as conn:
        # Создание таблицы если не существует
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                city TEXT,
                street TEXT,
                house TEXT,
                url TEXT
            )
        """)

        # Проверка и добавление отсутствующих колонок (миграция)
        cursor = conn.execute("PRAGMA table_info(users)")
        columns = {row[1] for row in cursor.fetchall()}

        # Добавляем full_name если отсутствует
        if "full_name" not in columns:
            print("🔄 Миграция: добавление колонки full_name")
            conn.execute("ALTER TABLE users ADD COLUMN full_name TEXT")

        # Добавляем url если отсутствует
        if "url" not in columns:
            print("🔄 Миграция: добавление колонки url")
            conn.execute(
                "ALTER TABLE users ADD COLUMN url TEXT DEFAULT 'https://www.dtek-dnem.com.ua/ua/shutdowns'"
            )

        conn.commit()


def user_exists(user_id: int) -> bool:
    """Проверка существования пользователя"""
    with get_db_connection() as conn:
        result = conn.execute(
            "SELECT 1 FROM users WHERE user_id = ? LIMIT 1", (user_id,)
        ).fetchone()
        return result is not None


def get_user_address(user_id: int) -> Optional[Tuple[str, str, str, str]]:
    """Получение данных пользователя (city, street, house, url)"""
    with get_db_connection() as conn:
        result = conn.execute(
            "SELECT city, street, house, url FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return result


def add_user(
    user_id: int,
    username: str,
    full_name: str,
    city: str,
    street: str,
    house: str,
    url: str,
):
    """Добавление или обновление пользователя"""
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO users (user_id, username, full_name, city, street, house, url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (user_id, username, full_name, city, street, house, url),
        )
        conn.commit()
