#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Оптимизированный Telegram бот для управления графиками отключений
"""

import asyncio
import os
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from database import init_db, user_exists, add_user, get_user_address
from cache import schedule_cache

# Загрузка переменных окружения
load_dotenv()

# Константы
API_TOKEN = os.getenv("API_TOKEN")
ADMIN_ID_STR = os.getenv("ADMIN_ID")


if not API_TOKEN:
    raise RuntimeError("API_TOKEN not set in environment")
if not ADMIN_ID_STR:
    raise RuntimeError("ADMIN_ID not set in environment")

ADMIN_ID = int(ADMIN_ID_STR)

# Пути к файлам
HTML_PATH = Path("dtek_shutdowns.html")
JSON_PATH = Path("today_schedule.json")
PNG_PATH = Path("today_schedule.png")
AUTOMATE_SCRIPT = "dtek_automate.py"

# Инициализация бота
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
init_db()

# Хранилище состояний
pending_requests: Dict[int, Dict[str, str]] = {}
pending_approvals: Dict[int, Dict[str, Any]] = {}

# Этапы одобрения
APPROVAL_STAGES = ["url", "city", "street", "house"]

# Клавиатуры
kb_next_day = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="График на завтра", callback_data="next_day")]
    ]
)


def cleanup_files(*files: Path) -> None:
    """Удаление файлов без ошибок"""
    for file in files:
        file.unlink(missing_ok=True)


def run_automate_script(city: str, street: str, house: str, url: str, next_day: bool = False) -> bool:
    """Запуск скрипта автоматизации с обработкой ошибок"""
    try:
        cmd = [
            "python3",
            AUTOMATE_SCRIPT,
            f'--city="{city}"',
            f'--street="{street}"',
            f'--house="{house}"',
            f'--url="{url}"'
        ]
        
        if next_day:
            cmd.append("--next-day")
            
        result = subprocess.run(
            " ".join(cmd),
            shell=True,
            check=True,
            capture_output=True,
            text=True
        )
        print(f"Automation script output: {result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error running automation script: {e}")
        print(f"Stderr: {e.stderr}")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False


def read_schedule(json_path: Path = JSON_PATH) -> Optional[List[Dict[str, str]]]:
    """Чтение графика из JSON файла"""
    if not json_path.exists():
        return None
    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"Ошибка чтения JSON: {e}")
        return None


def extract_off_intervals(schedule: List[Dict[str, str]]) -> List[Tuple[str, str]]:
    """Извлечение интервалов отключения света"""
    off_blocks = []
    current_start = None
    prev_end = None

    for item in schedule:
        start, end = item["interval"].split("-")

        if item["status"] == "off":
            if current_start is None:
                current_start = start
            prev_end = end
        else:
            if current_start is not None:
                off_blocks.append((current_start, prev_end))
                current_start = None

    if current_start is not None:
        off_blocks.append((current_start, prev_end))

    return off_blocks


def format_schedule(off_times: List[Tuple[str, str]], is_tomorrow: bool = False) -> str:
    """Форматирование графика для отображения"""
    if not off_times:
        return "Отключений света не запланировано."

    prefix = "Завтра света не будет: " if is_tomorrow else "Света не будет: "
    intervals = ", ".join(f"с {start} до {end}" for start, end in off_times)
    return prefix + intervals


async def send_admin_notification(user_id: int, username: str, address: str) -> bool:
    """Отправка уведомления админу о новой заявке"""
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Дать доступ", callback_data=f"approve_{user_id}"
                )
            ]
        ]
    )

    try:
        await bot.send_message(
            ADMIN_ID,
            f"Новая заявка!\nID: {user_id}\nUsername: @{username}\nАдрес: {address}",
            reply_markup=kb,
        )
        return True
    except Exception as e:
        print(f"❌ Ошибка отправки админу: {e}")
        return False


async def notify_user(user_id: int, message: str) -> bool:
    """Уведомление пользователя"""
    try:
        await bot.send_message(user_id, message)
        return True
    except Exception as e:
        print(f"❌ Не удалось уведомить пользователя {user_id}: {e}")
        return False


async def process_schedule_request(
    message: types.Message,
    city: str,
    street: str,
    house: str,
    url: str,
    next_day: bool = False,
) -> None:
    """Обработка запроса графика с кэшированием"""
    # 1. Сначала проверяем кэш
    cached_schedule = schedule_cache.get(city, street, house, url, next_day)
    
    if cached_schedule is not None:
        print(f"Используем кэшированные данные для {city}, {street}, {house}")
        off_times = extract_off_intervals(cached_schedule)
        result_text = format_schedule(off_times, next_day)
        reply_markup = kb_next_day if not next_day else None
        await message.answer(result_text, reply_markup=reply_markup)
        return

    # 2. Если в кэше нет, загружаем данные
    await message.answer(
        "⏳ Обновляю данные..." if not next_day else "⏳ Загружаю график на завтра..."
    )

    # 3. Запускаем парсинг
    cleanup_files(HTML_PATH, JSON_PATH, PNG_PATH)
    success = run_automate_script(city, street, house, url, next_day)
    
    if not success:
        await message.answer("❌ Не удалось загрузить данные. Попробуйте позже.")
        return

    # 4. Читаем и парсим данные
    schedule = read_schedule()
    if not schedule:
        await message.answer("❌ Не удалось прочитать расписание.")
        return

    # 5. Сохраняем в кэш
    schedule_cache.set(city, street, house, url, schedule, next_day)
    
    # 6. Формируем и отправляем ответ
    off_times = extract_off_intervals(schedule)
    result_text = format_schedule(off_times, next_day)
    reply_markup = kb_next_day if not next_day else None
    await message.answer(result_text, reply_markup=reply_markup)



# ==================== ОБРАБОТЧИКИ ====================


@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    """Обработчик команды /start"""
    if message.chat.type != "private":
        await message.reply("Пожалуйста, пишите боту в личные сообщения.")
        return

    user_id = message.from_user.id

    if not user_exists(user_id):
        await message.answer(
            "Перед началом использования введите ваш адрес:\n"
            "Название города или села, улица, номер дома"
        )
        return

    addr = get_user_address(user_id)
    if not addr:
        await message.answer("Ошибка: не удалось получить адрес из базы.")
        return

    await process_schedule_request(message, *addr)


@dp.message()
async def handle_messages(message: types.Message):
    """Обработчик всех текстовых сообщений"""
    if message.chat.type != "private":
        return

    user_id = message.from_user.id

    # Логика для админа
    if user_id == ADMIN_ID and ADMIN_ID in pending_approvals:
        await handle_admin_input(message)
        return

    # Логика для пользователя
    if not user_exists(user_id):
        await handle_user_request(message)


async def handle_admin_input(message: types.Message):
    """Обработка ввода данных админом"""
    state = pending_approvals[ADMIN_ID]
    stage = state.get("stage")
    text = message.text.strip()

    if stage == "url":
        state["url"] = text
        state["stage"] = "city"
        await message.answer("Введите город:")

    elif stage == "city":
        state["city"] = text
        state["stage"] = "street"
        await message.answer("Введите улицу:")

    elif stage == "street":
        state["street"] = text
        state["stage"] = "house"
        await message.answer("Введите номер дома:")

    elif stage == "house":
        state["house"] = text
        target_user = state["user_id"]
        username = state.get("username", "")
        full_name = state.get("full_name", "")

        add_user(
            target_user,
            username,
            full_name,
            state["city"],
            state["street"],
            text,
            state["url"],
        )
        del pending_approvals[ADMIN_ID]

        await message.answer(f"Пользователь {target_user} добавлен в базу данных 🎉")

        if not await notify_user(
            target_user, "Ваши данные обработаны. Нажмите /start."
        ):
            await message.answer(
                "Не удалось уведомить пользователя (возможно он заблокировал бота)."
            )


async def handle_user_request(message: types.Message):
    """Обработка заявки от пользователя"""
    user_id = message.from_user.id
    username = message.from_user.username or f"id{user_id}"
    full_name = message.from_user.full_name or ""
    address = message.text.strip()

    pending_requests[user_id] = {
        "username": username,
        "full_name": full_name,
        "address_raw": address,
    }

    if await send_admin_notification(user_id, username, address):
        await message.answer("Ваш индивидуальный график обрабатывается ✅")
    else:
        await message.answer(
            "Ваш индивидуальный график не удалось обработать. Попробуйте позже ❌"
        )


@dp.callback_query(lambda c: c.data and c.data.startswith("approve_"))
async def approve_callback(callback: CallbackQuery):
    """Обработка одобрения заявки админом"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return

    try:
        target_user_id = int(callback.data.split("_")[1])
    except (IndexError, ValueError):
        await callback.answer("Некорректные данные")
        return

    if target_user_id not in pending_requests:
        await callback.answer("Заявка не найдена или уже обработана.")
        return

    req = pending_requests[target_user_id]
    pending_approvals[ADMIN_ID] = {
        "user_id": target_user_id,
        "username": req["username"],
        "full_name": req["full_name"],
        "stage": "url",
    }

    await callback.message.answer(
        "Введите URL сайта для парсинга (например: https://www.dtek-dnem.com.ua/ua/shutdowns):"
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "next_day")
async def next_day_callback(callback: CallbackQuery):
    """Обработка запроса графика на завтра"""
    addr = get_user_address(callback.from_user.id)
    if not addr:
        await callback.message.answer("Ошибка: не удалось получить адрес из базы.")
        return

    await process_schedule_request(callback.message, *addr, next_day=True)


async def main():
    print("🤖 Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
