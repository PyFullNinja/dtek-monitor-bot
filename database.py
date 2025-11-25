import sqlite3
from pathlib import Path

DB_PATH = Path("user.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            city TEXT,
            street TEXT,
            house TEXT
        )
    """)
    conn.commit()
    conn.close()


def user_exists(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
    result = cur.fetchone()
    conn.close()
    return result is not None


def get_user_address(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT city, street, house FROM users WHERE user_id = ?", (user_id,))
    result = cur.fetchone()
    conn.close()
    return result  # (city, street, house)


def add_user(user_id: int, username: str, city: str, street: str, house: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO users (user_id, username, city, street, house)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, username, city, street, house))
    conn.commit()
    conn.close()

