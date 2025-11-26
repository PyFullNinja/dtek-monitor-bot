#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Полностью переписанный bot.py
- если пользователя нет в БД -> просит ввести адрес (в личных сообщениях)
- адрес отсылается админу с кнопкой "Дать доступ"
- админ нажимает -> бот в личке у админа последовательно спрашивает: город -> улица -> дом
- после ввода всех полей бот добавляет пользователя в sqlite и уведомляет его
- админ не получает лишних сообщений (обработчики разделены)
"""

import asyncio
import os
import json
import subprocess
from pathlib import Path
from typing import Dict, Any

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from database import init_db, user_exists, add_user, get_user_address

# Загружаем .env
load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
if ADMIN_ID is None:
    raise RuntimeError("ADMIN_ID not set in environment")
ADMIN_ID = int(ADMIN_ID)

if API_TOKEN is None:
    raise RuntimeError("API_TOKEN not set in environment")

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Пути и скрипты
HTML_PATH = Path("dtek_shutdowns.html")
JSON_PATH = Path("today_schedule.json")
PNG_PATH = Path("today_schedule.png")
AUTOMATE_SCRIPT = "dtek_automate.py"
PARSER_SCRIPT = "main.py"

# Инициализация БД
init_db()

# Временные структуры для ожиданий
# pending_requests: { user_id: {"username": str, "address_raw": str} }
pending_requests: Dict[int, Dict[str, Any]] = {}
# pending_approvals: { admin_id: {"user_id": int, "stage": "city"/"street"/"house", "city":..., "street":...} }
pending_approvals: Dict[int, Dict[str, Any]] = {}


def cleanup_old_files():
    for f in [HTML_PATH, JSON_PATH, PNG_PATH]:
        if f.exists():
            try:
                f.unlink()
            except Exception:
                pass


def run_automate_script(env: Dict[str, str]):
    """Запускаем playwright-скрипт с подставленными переменными окружения."""
    # передаём env copy, чтобы subprocess унаследовал CITY/STREET/HOUSE
    proc_env = os.environ.copy()
    proc_env.update(env)
    print("Запускаю", AUTOMATE_SCRIPT, "с переменными", {k: proc_env.get(k) for k in ("CITY","STREET","HOUSE")})
    result = subprocess.run(["python3", AUTOMATE_SCRIPT], capture_output=True, text=True, env=proc_env)
    print("automate stdout:", result.stdout)
    print("automate stderr:", result.stderr)


def read_schedule():
    if not JSON_PATH.exists():
        return None
    return json.loads(JSON_PATH.read_text(encoding="utf-8"))


def extract_off_intervals(schedule):
    off_blocks = []
    current_block_start = None
    prev_end = None

    for item in schedule:
        start, end = item["interval"].split("-")
        if item["status"] == "off":
            if current_block_start is None:
                current_block_start = start
            prev_end = end
        else:
            if current_block_start is not None:
                off_blocks.append((current_block_start, prev_end))
                current_block_start = None

    if current_block_start is not None:
        off_blocks.append((current_block_start, prev_end))

    return off_blocks


@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    # работаем только в личных сообщениях
    if message.chat.type != "private":
        await message.reply("Пожалуйста, пишите боту в личные сообщения.")
        return

    user_id = message.from_user.id

    # Если пользователь НЕ зарегистрирован — просим адрес
    if not user_exists(user_id):
        await message.answer(
            "Перед началом использования введите ваш адрес:\n"
            "Название города или села, улица, номер дома"
        )
        return

    # Получаем разложенный адрес из базы
    addr = get_user_address(user_id)
    if not addr:
        await message.answer("Ошибка: не удалось получить адрес из базы.")
        return

    city, street, house = addr

    await message.answer("⏳ Обновляю данные...")

    # Очищаем старые файлы
    cleanup_old_files()

    # Запускаем automate с нужными переменными
    env = {"CITY": city, "STREET": street, "HOUSE": house}
    run_automate_script(env)

    schedule = read_schedule()
    if not schedule:
        await message.answer("Ошибка: не удалось получить график.")
        return

    off_times = extract_off_intervals(schedule)
    if not off_times:
        await message.answer("Сегодня отключений света нет 🎉")
        return

    result_parts = [f"с {start} до {end}" for start, end in off_times]
    result_text = "Света не будет: " + ", ".join(result_parts)
    await message.answer(result_text)


@dp.message()
async def handle_messages(message: types.Message):
    """Главный обработчик входящих сообщений.

    Поведение:
    - если это админ и у него активный pending_approvals -> трактуем сообщение как ответ (city/street/house)
    - иначе если это НЕ админ и пользователь не в БД -> трактуем сообщение как заявка-адрес и шлём админу
    - в других случаях игнорируем/не перепутываем
    """
    # только личные сообщения
    if message.chat.type != "private":
        return

    user_id = message.from_user.id

    # ------------------- Админская логика -------------------
    if user_id == ADMIN_ID:
        # есть ли у админа активное одобрение
        if ADMIN_ID in pending_approvals:
            state = pending_approvals[ADMIN_ID]
            stage = state.get("stage")

            if stage == "city":
                state["city"] = message.text.strip()
                state["stage"] = "street"
                await message.answer("Введите улицу:")
                return

            if stage == "street":
                state["street"] = message.text.strip()
                state["stage"] = "house"
                await message.answer("Введите номер дома:")
                return

            if stage == "house":
                state["house"] = message.text.strip()
                target_user = state.get("user_id")
                username = state.get("username")

                # добавляем в базу
                add_user(target_user, username or "", state.get("city",""), state.get("street",""), state.get("house",""))

                # чистим state
                del pending_approvals[ADMIN_ID]

                await message.answer(f"Пользователь {target_user} добавлен в базу данных 🎉")

                # уведомляем пользователя
                try:
                    await bot.send_message(target_user, "Ваши данные обработаны. Нажмите /start.")
                except Exception:
                    # пользователь мог удалить бота или заблокировать
                    await message.answer("Не удалось уведомить пользователя (возможно он заблокировал бота).")
                return

        # если у админа нет активного ожидания — игнорируем
        return

    # ------------------- Пользовательская логика -------------------
    # если пользователь уже в БД — не считаем это заявкой
    if user_exists(user_id):
        # ничего не делаем (или можно обрабатывать другие команды)
        return

    # иначе — принимаем это сообщение как адрес-заявку (одной строкой)
    address_raw = message.text.strip()
    username = message.from_user.username or f"id{user_id}"

    # сохраняем временно
    pending_requests[user_id] = {"username": username, "address_raw": address_raw}

    # формируем кнопку для админа
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Дать доступ", callback_data=f"approve_{user_id}")]
    ])

    # отправляем админу
    try:
        await bot.send_message(
            ADMIN_ID,
            f"Новая заявка!\n ID: {user_id}\n Username: @{username}\n Адрес (raw): {address_raw}",
            reply_markup=kb,
        )
    except Exception as e:
        # если не получилось отправить админу — сообщаем пользователю и логируем
        await message.answer("Ваш индивидуальный график не удалось обработать. Попробуйте позже ❌")
        print("Failed to send admin message:", e)
        return

    await message.answer("Ваш индивидуальный график обрабатывается ✅")


@dp.callback_query(lambda c: c.data and c.data.startswith("approve_"))
async def approve_callback(callback: CallbackQuery):
    """Обработка нажатия админом кнопки 'Дать доступ'"""
    # только админ может нажимать
    from_user = callback.from_user
    if from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return

    # извлекаем user_id из callback
    try:
        target_user_id = int(callback.data.split("_")[1])
    except Exception:
        await callback.answer("Некорректные данные")
        return

    # есть ли такая pending заявка?
    if target_user_id not in pending_requests:
        await callback.answer("Заявка не найдена или уже обработана.")
        return

    # готовим state для админа
    req = pending_requests[target_user_id]
    pending_approvals[ADMIN_ID] = {"user_id": target_user_id, "username": req.get("username"), "stage": "city"}

    # можно удалить pending_requests — но лучше оставить до полного завершения
    # pending_requests.pop(target_user_id, None)

    # спрашиваем у админа город
    await callback.message.answer("Введите город:")
    await callback.answer()


async def main():
    print("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())


