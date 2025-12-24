#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Оптимизированный Telegram бот с асинхронным парсингом
"""

import asyncio
import json
from typing import Dict, Any, Optional, Tuple, List

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

import config
from database import init_db, user_exists, add_user, get_user_address, get_user_count
from cache import schedule_cache
from parser_service import parser_service, TaskStatus


# ======================
# Инициализация
# ======================
bot = Bot(token=config.API_TOKEN)
dp = Dispatcher()
init_db()

# Хранилище состояний
pending_requests: Dict[int, Dict[str, str]] = {}
pending_approvals: Dict[int, Dict[str, Any]] = {}
active_parsings: Dict[int, str] = {}  # user_id -> task_id


# ======================
# Клавиатуры
# ======================

def get_main_keyboard() -> InlineKeyboardMarkup:
    """Главная клавиатура"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="График на завтра", callback_data="next_day")],
            # [InlineKeyboardButton(text="🔄 Обновить сейчас", callback_data="refresh")],
        ]
    )


# ======================
# Вспомогательные функции
# ======================

def read_schedule() -> Optional[List[Dict[str, str]]]:
    """Чтение графика из JSON файла"""
    if not config.JSON_PATH.exists():
        return None
    try:
        return json.loads(config.JSON_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"❌ Ошибка чтения JSON: {e}")
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
        emoji = "✅"
        message = "Отключений света не запланировано"
        return f"{emoji} {message}!"

    emoji = "" if not is_tomorrow else "⏳"
    prefix = "Завтра света не будет" if is_tomorrow else "Сегодня света не будет"
    intervals = ", ".join(f"с {start} до {end}" for start, end in off_times)

    return f"{emoji} {prefix}:\n{intervals}"


async def send_admin_notification(user_id: int, username: str, address: str) -> bool:
    """Отправка уведомления админу о новой заявке"""
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Дать доступ",
                    callback_data=f"approve_{user_id}"
                )
            ]
        ]
    )

    try:
        await bot.send_message(
            config.ADMIN_ID,
            f"📩 Новая заявка!\n\n"
            f"ID: {user_id}\n"
            f"Username: @{username}\n"
            f"Адрес: {address}",
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


async def update_parsing_progress(user_id: int, msg: types.Message, task_id: str):
    """
    Обновление прогресса парсинга в реальном времени
    """
    progress_emojis = ["⏳", "⏳", "⏳","⏳"]
    emoji_idx = 0

    while True:
        task = parser_service.get_task_status(task_id)

        if not task:
            break

        # Обновляем сообщение с прогрессом
        try:
            emoji = progress_emojis[emoji_idx % len(progress_emojis)]
            await msg.edit_text(f"{emoji} {task.progress}")
            emoji_idx += 1
        except Exception:
            pass

        # Если задача завершена - выходим
        if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
            break

        await asyncio.sleep(0.5)


async def process_schedule_request(
    message: types.Message,
    city: str,
    street: str,
    house: str,
    url: str,
    next_day: bool = False,
) -> None:
    """
    Оптимизированная обработка запроса графика

    Изменения:
    - Асинхронный парсинг через parser_service
    - Обновление прогресса в реальном времени
    - Неблокирующее выполнение
    """
    user_id = message.from_user.id

    # 1. Проверяем кэш
    cached_schedule = schedule_cache.get(city, street, house, url, next_day)

    if cached_schedule is not None:
        print(f"💾 Используем кэш для {city}, {street}, {house}")
        off_times = extract_off_intervals(cached_schedule)
        result_text = format_schedule(off_times, next_day)
        await message.answer(result_text, reply_markup=get_main_keyboard())
        return

    # 2. Запускаем асинхронный парсинг
    status_msg = await message.answer("⏳ Обновляю данные...")

    # Callback для обновления после завершения парсинга
    async def on_parsing_complete(task):
        try:
            if task.status == TaskStatus.COMPLETED:
                schedule = read_schedule()

                if schedule:
                    # Сохраняем в кэш
                    schedule_cache.set(city, street, house, url, schedule, next_day)

                    # Удаляем сообщение о прогрессе
                    try:
                        await status_msg.delete()
                    except Exception:
                        pass

                    # Отправляем результат новым сообщением
                    off_times = extract_off_intervals(schedule)
                    result_text = format_schedule(off_times, next_day)
                    await message.answer(result_text, reply_markup=get_main_keyboard())
                else:
                    await status_msg.edit_text("Не удалось прочитать расписание.")

            elif task.status == TaskStatus.FAILED:
                error_text = (
                    "Не удалось загрузить данные с сайта DTEK.\n"
                    "Попробуйте позже."
                )
                if task.error:
                    error_text += f"\n\nОшибка: {task.error}"

                await status_msg.edit_text(error_text)

        except Exception as e:
            print(f"❌ Ошибка в callback: {e}")
        finally:
            # Удаляем из активных парсингов
            if user_id in active_parsings:
                del active_parsings[user_id]

    # 3. Отправляем задачу в очередь
    task_id = await parser_service.submit_task(
        city, street, house, url, next_day, on_parsing_complete
    )

    active_parsings[user_id] = task_id

    # 4. Обновляем прогресс в реальном времени
    await update_parsing_progress(user_id, status_msg, task_id)


# ======================
# Обработчики команд
# ======================

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    """Обработчик команды /start"""
    if message.chat.type != "private":
        await message.reply("⚠️ Пожалуйста, пишите боту в личные сообщения.")
        return

    user_id = message.from_user.id

    if not user_exists(user_id):
        await message.answer(
            "👋 Привет! Я бот для отслеживания графиков отключений DTEK.\n\n"
            "Для начала работы введите ваш адрес в формате:\n"
            "Город, Улица, Номер дома\n\n"
            "Например: Днепр, Набережная Победы, 50а"
        )
        return

    addr = get_user_address(user_id)
    if not addr:
        await message.answer("Не удалось получить адрес из базы.")
        return

    await process_schedule_request(message, *addr)


@dp.message(Command("stats"))
async def stats_cmd(message: types.Message):
    """Статистика бота (только для админа)"""
    if message.from_user.id != config.ADMIN_ID:
        return

    parser_stats = parser_service.get_stats()
    cache_stats = schedule_cache.get_stats()
    user_count = get_user_count()

    stats_text = (
        "📊 Статистика бота\n\n"
        f"👥 Пользователей: {user_count}\n\n"
        f"🔧 Парсер:\n"
        f"  • Очередь: {parser_stats['queue_size']}\n"
        f"  • Активных: {parser_stats['active_tasks']}\n"
        f"  • Завершено: {parser_stats['completed']}\n"
        f"  • Ошибок: {parser_stats['failed']}\n"
        f"  • Воркеров: {parser_stats['workers']}\n\n"
        f"💾 Кэш:\n"
        f"  • Размер: {cache_stats['size']}/{cache_stats['max_size']}\n"
        f"  • TTL: {cache_stats['ttl_minutes']} мин"
    )

    await message.answer(stats_text)


@dp.message()
async def handle_messages(message: types.Message):
    """Обработчик всех текстовых сообщений"""
    if message.chat.type != "private":
        return

    user_id = message.from_user.id

    # Логика для админа (процесс одобрения)
    if user_id == config.ADMIN_ID and config.ADMIN_ID in pending_approvals:
        await handle_admin_input(message)
        return

    # Логика для нового пользователя
    if not user_exists(user_id):
        await handle_user_request(message)


async def handle_admin_input(message: types.Message):
    """Обработка ввода данных админом"""
    state = pending_approvals[config.ADMIN_ID]
    stage = state.get("stage")
    text = message.text.strip()

    if stage == "url":
        state["url"] = text
        state["stage"] = "city"
        await message.answer("🏙️ Введите город:")

    elif stage == "city":
        state["city"] = text
        state["stage"] = "street"
        await message.answer("🛣️ Введите улицу:")

    elif stage == "street":
        state["street"] = text
        state["stage"] = "house"
        await message.answer("🏠 Введите номер дома:")

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

        del pending_approvals[config.ADMIN_ID]

        await message.answer(f"✅ Пользователь {target_user} добавлен в базу данных!")

        if not await notify_user(target_user, "✅ Ваши данные обработаны! Нажмите /start"):
            await message.answer(
                "⚠️ Не удалось уведомить пользователя (возможно, он заблокировал бота)."
            )


async def handle_user_request(message: types.Message):
    """Обработка заявки от нового пользователя"""
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
        await message.answer(
            "✅ Ваша заявка отправлена администратору.\n"
            "Ожидайте одобрения..."
        )
    else:
        await message.answer(
            "❌ Не удалось отправить заявку администратору.\n"
            "Попробуйте позже."
        )


# ======================
# Обработчики callback
# ======================

@dp.callback_query(lambda c: c.data and c.data.startswith("approve_"))
async def approve_callback(callback: CallbackQuery):
    """Обработка одобрения заявки админом"""
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    try:
        target_user_id = int(callback.data.split("_")[1])
    except (IndexError, ValueError):
        await callback.answer("❌ Некорректные данные")
        return

    if target_user_id not in pending_requests:
        await callback.answer("⚠️ Заявка не найдена или уже обработана.")
        return

    req = pending_requests[target_user_id]
    pending_approvals[config.ADMIN_ID] = {
        "user_id": target_user_id,
        "username": req["username"],
        "full_name": req["full_name"],
        "stage": "url",
    }

    await callback.message.answer(
        "🔗 Введите URL сайта для парсинга\n"
        f"(по умолчанию: {config.DEFAULT_DTEK_URL}):"
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "next_day")
async def next_day_callback(callback: CallbackQuery):
    """Обработка запроса графика на завтра"""
    addr = get_user_address(callback.from_user.id)
    if not addr:
        await callback.message.answer("❌ Ошибка: не удалось получить адрес из базы.")
        return

    await process_schedule_request(callback.message, *addr, next_day=True)
    await callback.answer()


@dp.callback_query(lambda c: c.data == "refresh")
async def refresh_callback(callback: CallbackQuery):
    """Принудительное обновление графика (игнорируя кэш)"""
    addr = get_user_address(callback.from_user.id)
    if not addr:
        await callback.message.answer("❌ Ошибка: не удалось получить адрес из базы.")
        return

    # Очищаем кэш для этого адреса
    city, street, house, url = addr
    schedule_cache.cache.pop(
        schedule_cache._make_key(city, street, house, url, False),
        None
    )

    await process_schedule_request(callback.message, *addr, next_day=False)
    await callback.answer("🔄 Обновляю данные...")


# ======================
# Запуск бота
# ======================

async def main():
    print("🤖 Бот запущен")
    print(f"📊 Админ ID: {config.ADMIN_ID}")
    print(f"💾 База данных: {config.DB_PATH}")
    print(f"⏱️ Кэш TTL: {config.CACHE_TTL_MINUTES} минут")

    # Запускаем parser service
    await parser_service.start()

    try:
        await dp.start_polling(bot)
    finally:
        # Останавливаем parser service
        await parser_service.stop()


if __name__ == "__main__":
    asyncio.run(main())
