#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Работа с базой данных SQLite
"""

import sqlite3
from contextlib import contextmanager
from typing import Optional, Tuple

import config


@contextmanager
def get_db_connection():
    """Контекстный менеджер для безопасной работы с БД"""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row  # Доступ к колонкам по имени
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
                city TEXT NOT NULL,
                street TEXT NOT NULL,
                house TEXT NOT NULL,
                url TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                f"ALTER TABLE users ADD COLUMN url TEXT DEFAULT '{config.DEFAULT_DTEK_URL}'"
            )

        # Добавляем временные метки если отсутствуют
        if "created_at" not in columns:
            print("🔄 Миграция: добавление колонки created_at")
            conn.execute(
                "ALTER TABLE users ADD COLUMN created_at TIMESTAMP"
            )
            conn.execute(
                "UPDATE users SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"
            )


        if "updated_at" not in columns:
            print("🔄 Миграция: добавление колонки updated_at")
            conn.execute(
                "ALTER TABLE users ADD COLUMN updated_at TIMESTAMP"
            )
            conn.execute(
                "UPDATE users SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL"
            )


        conn.commit()
        print(f"✅ База данных инициализирована: {config.DB_PATH}")


def user_exists(user_id: int) -> bool:
    """Проверка существования пользователя"""
    with get_db_connection() as conn:
        result = conn.execute(
            "SELECT 1 FROM users WHERE user_id = ? LIMIT 1",
            (user_id,)
        ).fetchone()
        return result is not None


def get_user_address(user_id: int) -> Optional[Tuple[str, str, str, str]]:
    """
    Получение данных пользователя (city, street, house, url)

    Returns:
        Tuple[city, street, house, url] или None
    """
    with get_db_connection() as conn:
        result = conn.execute(
            "SELECT city, street, house, url FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()

        if result:
            return tuple(result)
        return None


def add_user(
    user_id: int,
    username: str,
    full_name: str,
    city: str,
    street: str,
    house: str,
    url: str,
) -> bool:
    """
    Добавление или обновление пользователя

    Returns:
        True если успешно, False при ошибке
    """
    try:
        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO users (user_id, username, full_name, city, street, house, url, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    full_name = excluded.full_name,
                    city = excluded.city,
                    street = excluded.street,
                    house = excluded.house,
                    url = excluded.url,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, username, full_name, city, street, house, url),
            )
            conn.commit()
            print(f"✅ Пользователь {user_id} добавлен/обновлен в БД")
            return True
    except Exception as e:
        print(f"❌ Ошибка добавления пользователя: {e}")
        return False


def get_user_count() -> int:
    """Получение количества пользователей"""
    with get_db_connection() as conn:
        result = conn.execute("SELECT COUNT(*) FROM users").fetchone()
        return result[0] if result else 0


def delete_user(user_id: int) -> bool:
    """Удаление пользователя из БД"""
    try:
        with get_db_connection() as conn:
            conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            conn.commit()
            print(f"✅ Пользователь {user_id} удалён из БД")
            return True
    except Exception as e:
        print(f"❌ Ошибка удаления пользователя: {e}")
        return False
