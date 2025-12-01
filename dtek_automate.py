#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Оптимизированный скрипт автоматизации работы с сайтом DTEK
"""

import os
import sys
import time
import subprocess
from pathlib import Path
from typing import Optional
from playwright.sync_api import sync_playwright, Locator, Page

# Константы
OUTPATH = Path("dtek_shutdowns.html")
URL = "https://www.dtek-dnem.com.ua/ua/shutdowns"
HEADLESS = False
DEFAULT_TIMEOUT = 5000


def safe_click(locator: Locator, timeout: int = 3000) -> bool:
    """Безопасный клик по элементу"""
    try:
        locator.click(timeout=timeout)
        return True
    except Exception:
        return False


def close_modal(page: Page) -> None:
    """Закрытие модального окна предупреждения"""
    selectors = [
        "button.modal__close.m-attention__close",
        "button[aria-label='close']",
        "button[class*='modal__close']",
    ]

    for selector in selectors:
        try:
            modal = page.locator(selector)
            if modal.count() > 0:
                safe_click(modal.first)
                time.sleep(0.5)
                return
        except Exception:
            continue


def fill_autocomplete(page: Page, field_id: str, value: str, search_text: str) -> bool:
    """Заполнение поля с автодополнением"""
    try:
        page.fill(f"#{field_id}", value)
        page.wait_for_timeout(600)

        # Попытка клика по выделенному элементу
        strong = page.locator(f'strong:has-text("{search_text}")')
        if strong.count() > 0:
            strong.first.click(timeout=DEFAULT_TIMEOUT)
            return True

        # Fallback: клик по первому элементу списка
        suggestions = page.locator("ul[role='listbox'] li")
        if suggestions.count() > 0:
            suggestions.first.click(timeout=DEFAULT_TIMEOUT)
            return True

        return False
    except Exception as e:
        print(f"⚠️ Ошибка при заполнении {field_id}: {e}")
        return False


def submit_form(page: Page) -> None:
    """Отправка формы поиска"""
    try:
        submit_selectors = [
            "button[type='submit']",
            "button.search-button",
            "button.btn--search",
        ]

        for selector in submit_selectors:
            submit = page.locator(selector)
            if submit.count() > 0:
                submit.first.click(timeout=3000)
                return

        # Fallback: Enter в поле дома
        page.press("#house_num", "Enter")
    except Exception:
        pass


def wait_for_results(page: Page) -> None:
    """Ожидание загрузки результатов"""
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        time.sleep(2)


def save_html(page: Page, next_day: bool) -> None:
    """Сохранение HTML страницы"""
    if next_day:
        try:
            page.locator("div.date", has_text="на завтра").click()
            time.sleep(1)
        except Exception as e:
            print(f"⚠️ Не удалось переключить на завтра: {e}")

    html = page.content()
    OUTPATH.write_text(html, encoding="utf-8")
    print(f"✅ HTML сохранён в: {OUTPATH}")


def run_parser() -> bool:
    """Запуск локального парсера"""
    commands = [
        [sys.executable, "main", str(OUTPATH)],
        [sys.executable, "main.py", str(OUTPATH)],
        ["python3", "main.py", str(OUTPATH)],
    ]

    print("🔹 Запуск парсера...")

    for cmd in commands:
        try:
            result = subprocess.run(
                cmd, check=False, capture_output=True, text=True, timeout=120
            )

            if result.returncode == 0:
                print(f"✅ Парсер выполнен: {' '.join(cmd)}")
                return True

            print(f"⚠️ Команда {' '.join(cmd)} вернула код {result.returncode}")

        except FileNotFoundError:
            continue
        except subprocess.TimeoutExpired:
            print("⚠️ Таймаут парсера (120s)")
            continue
        except Exception as e:
            print(f"⚠️ Ошибка: {e}")
            continue

    print("❌ Не удалось запустить парсер автоматически")
    return False


def main():
    # Получение параметров из окружения
    city = os.getenv("CITY")
    street = os.getenv("STREET")
    house = os.getenv("HOUSE")
    next_day = os.getenv("NEXT_DAY", "0") == "1"

    if not all([city, street, house]):
        print("❌ Ошибка: не заданы CITY, STREET или HOUSE")
        sys.exit(1)

    print("🟦 Параметры автоматизации:")
    print(f"   Город: {city}")
    print(f"   Улица: {street}")
    print(f"   Дом: {house}")
    print(f"   Завтра: {next_day}\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context()
        page = context.new_page()

        print(f"🌐 Открываю {URL}")
        page.goto(URL, wait_until="domcontentloaded", timeout=30000)

        # Закрытие модального окна
        close_modal(page)

        # Заполнение формы
        print(f"📝 Заполняю форму...")
        fill_autocomplete(page, "city", city, city.split()[-1])
        fill_autocomplete(page, "street", street, street.split()[0])

        try:
            page.fill("#house_num", house)
            page.wait_for_timeout(500)

            suggestions = page.locator("ul[role='listbox'] li")
            if suggestions.count() > 0:
                suggestions.first.click(timeout=4000)
            else:
                page.press("#house_num", "Enter")
        except Exception as e:
            print(f"⚠️ Ошибка при вводе дома: {e}")

        # Отправка формы
        submit_form(page)
        wait_for_results(page)

        # Сохранение результата
        save_html(page, next_day)

        context.close()
        browser.close()

    # Запуск парсера
    run_parser()
    print("✅ Готово")


if __name__ == "__main__":
    main()
