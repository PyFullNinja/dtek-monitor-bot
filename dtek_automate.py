#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Автоматизация работы с сайтом DTEK через Playwright
"""

import sys
import time
import subprocess
from pathlib import Path
from typing import Optional
from playwright.sync_api import sync_playwright, Locator, Page

import config


class DTEKAutomation:
    """Класс для автоматизации работы с сайтом DTEK"""

    def __init__(
        self,
        city: str,
        street: str,
        house: str,
        url: str,
        next_day: bool = False
    ):
        self.city = city
        self.street = street
        self.house = house
        self.url = url
        self.next_day = next_day

    def _close_modal(self, page: Page) -> None:
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
                    modal.first.click(timeout=3000)
                    time.sleep(0.5)
                    return
            except Exception:
                continue

    def _fill_autocomplete(
        self,
        page: Page,
        field_id: str,
        value: str,
        search_text: str
    ) -> bool:
        """Заполнение поля с автодополнением"""
        try:
            page.fill(f"#{field_id}", value)
            page.wait_for_timeout(600)

            # Попытка клика по выделенному элементу
            strong = page.locator(f'strong:has-text("{search_text}")')
            if strong.count() > 0:
                strong.first.click(timeout=5000)
                return True

            # Fallback: клик по первому элементу списка
            suggestions = page.locator("ul[role='listbox'] li")
            if suggestions.count() > 0:
                suggestions.first.click(timeout=5000)
                return True

            return False
        except Exception as e:
            print(f"⚠️ Ошибка при заполнении {field_id}: {e}")
            return False

    def _submit_form(self, page: Page) -> None:
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
        except Exception as e:
            print(f"⚠️ Ошибка отправки формы: {e}")

    def _save_html(self, page: Page) -> None:
        """Сохранение HTML страницы"""
        if self.next_day:
            try:
                page.locator("div.date", has_text="на завтра").click()
                time.sleep(1)
            except Exception as e:
                print(f"⚠️ Не удалось переключить на завтра: {e}")

        html = page.content()
        config.HTML_PATH.write_text(html, encoding="utf-8")
        print(f"✅ HTML сохранён: {config.HTML_PATH}")

    def run(self) -> bool:
        """Основной метод запуска автоматизации"""
        print("🟦 Параметры автоматизации:")
        print(f"   URL: {self.url}")
        print(f"   Город: {self.city}")
        print(f"   Улица: {self.street}")
        print(f"   Дом: {self.house}")
        print(f"   Завтра: {self.next_day}\n")

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=config.HEADLESS_BROWSER)
                context = browser.new_context()
                page = context.new_page()

                print(f"🌐 Открываю {self.url}")
                page.goto(
                    self.url,
                    wait_until="domcontentloaded",
                    timeout=config.BROWSER_TIMEOUT
                )

                # Закрытие модального окна
                self._close_modal(page)

                # Заполнение формы
                print("📝 Заполняю форму...")
                self._fill_autocomplete(
                    page, "city", self.city, self.city.split()[-1]
                )
                self._fill_autocomplete(
                    page, "street", self.street, self.street.split()[0]
                )

                # Заполнение номера дома
                try:
                    page.fill("#house_num", self.house)
                    page.wait_for_timeout(500)

                    suggestions = page.locator("ul[role='listbox'] li")
                    if suggestions.count() > 0:
                        suggestions.first.click(timeout=4000)
                    else:
                        page.press("#house_num", "Enter")
                except Exception as e:
                    print(f"⚠️ Ошибка при вводе дома: {e}")

                # Отправка формы
                self._submit_form(page)

                # Ожидание загрузки результатов
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    time.sleep(2)

                # Сохранение результата
                self._save_html(page)

                context.close()
                browser.close()

            # Запуск парсера
            return self._run_parser()

        except Exception as e:
            print(f"❌ Ошибка автоматизации: {e}")
            return False

    def _run_parser(self) -> bool:
        """Запуск парсера HTML → JSON"""
        commands = [
            [sys.executable, "main.py", str(config.HTML_PATH)],
            ["python3", "main.py", str(config.HTML_PATH)],
        ]

        print("🔹 Запуск парсера...")

        for cmd in commands:
            try:
                result = subprocess.run(
                    cmd,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=config.PARSER_TIMEOUT
                )

                if result.returncode == 0:
                    print(f"✅ Парсер выполнен: {' '.join(cmd)}")
                    return True

                print(f"⚠️ Команда {' '.join(cmd)} вернула код {result.returncode}")

            except FileNotFoundError:
                continue
            except subprocess.TimeoutExpired:
                print(f"⚠️ Таймаут парсера ({config.PARSER_TIMEOUT}s)")
                continue
            except Exception as e:
                print(f"⚠️ Ошибка: {e}")
                continue

        print("❌ Не удалось запустить парсер")
        return False


def main():
    """CLI интерфейс для dtek_automate.py"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Автоматизация парсинга графиков DTEK"
    )
    parser.add_argument("--city", required=True, help="Город")
    parser.add_argument("--street", required=True, help="Улица")
    parser.add_argument("--house", required=True, help="Номер дома")
    parser.add_argument(
        "--url",
        default=config.DEFAULT_DTEK_URL,
        help="URL сайта DTEK"
    )
    parser.add_argument(
        "--next-day",
        action="store_true",
        help="Получить график на завтра"
    )

    args = parser.parse_args()

    # Удаление кавычек из аргументов (если есть)
    city = args.city.strip('"\'')
    street = args.street.strip('"\'')
    house = args.house.strip('"\'')
    url = args.url.strip('"\'')

    automation = DTEKAutomation(city, street, house, url, args.next_day)
    success = automation.run()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
