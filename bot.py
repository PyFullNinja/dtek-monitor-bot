import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from pathlib import Path
import subprocess
import json
import os
import sqlite3
from dotenv import load_dotenv
from whitelist import WHITELIST

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")


bot = Bot(API_TOKEN)
dp = Dispatcher()

# Пути к файлам
HTML_PATH = Path("/mnt/data/dtek_shutdowns.html")
JSON_PATH = Path("today_schedule.json")
PNG_PATH = Path("today_schedule.png")

AUTOMATE_SCRIPT = "dtek_automate.py"  # playwright-скрипт
PARSER_SCRIPT = "main.py"  # ваш парсер


def cleanup_old_files():
    """Удаляет старые результаты, чтобы ничего не путалось."""
    for f in [HTML_PATH, JSON_PATH, PNG_PATH]:
        if f.exists():
            try:
                f.unlink()
                print(f"Удалён старый файл: {f}")
            except Exception as e:
                print(f"Не удалось удалить {f}: {e}")


def run_automate_script():
    """Запускает ваш playwright-скрипт."""
    print("Запускаю dtek_automate.py...")
    result = subprocess.run(
        ["python3", AUTOMATE_SCRIPT], capture_output=True, text=True
    )
    print("STDOUT automate:\n", result.stdout)
    print("STDERR automate:\n", result.stderr)


def read_schedule():
    """Читает JSON, созданный парсером."""
    if not JSON_PATH.exists():
        return None
    return json.loads(JSON_PATH.read_text(encoding="utf-8"))


def extract_off_intervals(schedule):
    """Собирает интервалы, когда света нет (объединяет подряд идущие)."""
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
    # проверка доступа
    if message.from_user.id not in WHITELIST:
        await message.answer("⛔ У вас нет доступа к этому боту.")
        return
    # elif message.chat.type != "private":
    #    await message.answer("⛔ Этот бот работает только в личных сообщениях.")
    #    return
    await message.answer("⏳ Обновляю данные...")

    # 1. очистить старые файлы
    cleanup_old_files()

    # 2. Запустить playwright и парсер
    run_automate_script()

    # 3. Прочитать json от парсера
    schedule = read_schedule()

    if not schedule:
        await message.answer("Ошибка: не удалось получить график.")
        return

    # 4. Извлечь интервалы отключений
    off_times = extract_off_intervals(schedule)

    if not off_times:
        await message.answer("Сегодня отключений света нет 🎉")
        return

    result_parts = [f"с {start} до {end}" for start, end in off_times]
    result_text = "Света не будет: " + ", ".join(result_parts)

    await message.answer(result_text)


async def main():
    print("Telegram bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
