#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dtek_automate.py
Автоматизация ввода на https://www.dtek-dnem.com.ua/ua/shutdowns с помощью Playwright (sync).
Сохраняет страницу в /mnt/data/dtek_shutdowns.html и запускает локальный парсер "main".
"""

import time
import subprocess
import sys
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from dotenv import load_dotenv


# --- настройки ---
load_dotenv()
URL = os.getenv("URL")
OUTPATH = Path(os.getenv("OUTPATH"))
CITY = os.getenv("CITY")
STREET = os.getenv("STREET")
HOUSE = os.getenv("HOUSE")
HEADLESS = True  # поставьте False для визуального дебага
# -----------------


def safe_click(locator, timeout=3000):
    try:
        locator.click(timeout=timeout)
        return True
    except PWTimeout:
        return False
    except Exception:
        return False


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context()
        page = context.new_page()

        print("Открываю страницу...", URL)
        page.goto(URL, wait_until="domcontentloaded", timeout=30000)

        # 1) Попробовать закрыть модалку, если она есть
        try:
            # подстраховки: 2 варианта селекторов
            btn = page.locator("button.modal__close.m-attention__close")
            if btn.count() > 0:
                print("Найдено окно внимания — закрываю.")
                safe_click(btn.first, timeout=5000)
                time.sleep(0.5)
            else:
                # возможный альтернативный селектор
                alt = page.locator(
                    "button[aria-label='close'], button[class*='modal__close']"
                )
                if alt.count() > 0:
                    print("Найден альтернативный селектор закрытия — кликаю.")
                    safe_click(alt.first, timeout=3000)
        except Exception as e:
            print("Ошибка при попытке закрыть модал (игнорирую):", e)

        # 2) Ввод города и выбор первого варианта
        try:
            print(f"Ввожу город: {CITY}")
            page.fill("#city", CITY)
            # ждём выпадашку — часто появляются <ul role=listbox> или .suggest...
            # сначала даём немного времени на появление
            page.wait_for_timeout(500)  # 0.5s
            # пытаемся выбрать элемент с текстом 'Дніпро' (регистронезависимо)
            if page.locator('strong:has-text("Дніпро")').count() > 0:
                page.locator('strong:has-text("Дніпро")').first.click(timeout=5000)
                print("Выбран вариант по strong: Дніпро")
            else:
                # fallback: кликаем первый элемент списка подсказок
                if page.locator("ul[role='listbox'] li").count() > 0:
                    page.locator("ul[role='listbox'] li").first.click(timeout=5000)
                    print("Выбран первый вариант в списке подсказок (fallback).")
                else:
                    print("Подсказки для города не найдены — продолжаю.")
            time.sleep(0.5)
        except Exception as e:
            print("Ошибка при выборе города (игнорируется):", e)

        # 3) Ввод улицы и выбор первого варианта
        try:
            print(f"Ввожу улицу: {STREET}")
            page.fill("#street", STREET)
            page.wait_for_timeout(500)
            # ищем любые подсказки — выбираем первый
            if page.locator('strong:has-text("Героїв")').count() > 0:
                page.locator('strong:has-text("Героїв")').first.click(timeout=5000)
                print("Выбран вариант улицы (по strong).")
            elif page.locator("ul[role='listbox'] li").count() > 0:
                page.locator("ul[role='listbox'] li").first.click(timeout=5000)
                print("Выбран первый вариант в списке подсказок для улицы (fallback).")
            else:
                print("Подсказки для улицы не найдены — продолжаю.")
            time.sleep(0.5)
        except Exception as e:
            print("Ошибка при выборе улицы (игнорируется):", e)

        # 4) Ввод номера дома и выбор первого варианта
        try:
            print(f"Ввожу номер дома: {HOUSE}")
            page.fill("#house_num", HOUSE)
            page.wait_for_timeout(400)
            # иногда в подсказках li содержит текст номера — берем первый
            if page.locator("ul[role='listbox'] li").count() > 0:
                page.locator("ul[role='listbox'] li").first.click(timeout=4000)
                print("Выбран первый вариант номера дома (если был).")
            else:
                # иногда нужно нажать Enter, чтобы применить значение
                page.press("#house_num", "Enter")
                print("Нажат Enter на поле house_num.")
            time.sleep(1.0)
        except Exception as e:
            print("Ошибка при выборе номера дома (игнорируется):", e)

        # 5) Подтвердить/отправить форму если есть кнопка submit (optional)
        try:
            # ищем видимую кнопку поиска/показа результатов
            submit_sel = (
                "button[type='submit'], button.search-button, button.btn--search"
            )
            if page.locator(submit_sel).count() > 0:
                page.locator(submit_sel).first.click(timeout=3000)
                print("Нажата кнопка submit (если была).")
            else:
                # если нет — пробуем press Enter на последнем поле
                page.press("#house_num", "Enter")
                print("Enter отправлен на поле house_num (fallback submit).")
        except Exception:
            pass

        # Подождём загрузки результатов — ждём networkidle или небольшую паузу
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            # fallback: небольшая пауза
            time.sleep(2)

        # 6) Сохраним текущий HTML в файл
        html = page.content()
        OUTPATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPATH.write_text(html, encoding="utf-8")
        print(f"Сохранён HTML в {OUTPATH}")

        # закрываем браузер
        context.close()
        browser.close()

    # 7) Запускаем локальный парсер "main" (в текущей папке).
    # Попробуем несколько вариантов вызова: sys.executable + 'main', затем 'main.py'
    invoked = False
    try_cmds = [
        [sys.executable, "main", str(OUTPATH)],
        [sys.executable, "main.py", str(OUTPATH)],
        ["python", "main", str(OUTPATH)],
        ["python3", "main", str(OUTPATH)],
        ["python", "main.py", str(OUTPATH)],
        ["python3", "main.py", str(OUTPATH)],
    ]
    print("Пробую запустить локальный парсер из текущей папки (main)...")
    for cmd in try_cmds:
        try:
            print("Выполняю:", " ".join(cmd))
            res = subprocess.run(
                cmd, check=False, capture_output=True, text=True, timeout=120
            )
            print("--- STDOUT ---")
            print(res.stdout.strip())
            print("--- STDERR ---")
            print(res.stderr.strip())
            if res.returncode == 0:
                print("Парсер успешно выполнился с командой:", " ".join(cmd))
                invoked = True
                break
            else:
                print(
                    f"Команда вернула код {res.returncode}, пробую следующий вариант..."
                )
        except FileNotFoundError:
            # интерпретатор/файл не найден — пробуем следующий
            continue
        except subprocess.TimeoutExpired:
            print("Запуск парсера превысил таймаут (120s).")
            continue
        except Exception as e:
            print("Ошибка при запуске парсера:", e)
            continue

    if not invoked:
        print(
            "Не удалось автоматически запустить 'main'. Убедитесь, что в текущей папке существует исполняемый файл 'main' или 'main.py'."
        )
        print("Вы можете вручную выполнить: python main /mnt/data/dtek_shutdowns.html")


if __name__ == "__main__":
    main()
