#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import time
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import subprocess

# === файл HTML, куда будет сохранён результат ===
OUTPATH = Path("dtek_shutdowns.html")

# === playwright debug ===
HEADLESS = False   # False → для визуальной отладки


def safe_click(locator, timeout=3000):
    try:
        locator.click(timeout=timeout)
        return True
    except Exception:
        return False


def main():
    # -----------------------------
    #    ПАРАМЕТРЫ КОМАНДНОЙ СТРОКИ
    # -----------------------------
    #if len(sys.argv) != 4:
    #    print("Использование:")
    #    print("  python dtek_automate.py \"Город\" \"Улица\" \"Дом\"")
    #    print()
    #    print("Например:")
    #    print("  python dtek_automate.py \"М. Дніпро\" \"просп. Героїв\" \"8\"")
    #    sys.exit(1)

    CITY = os.getenv("CITY")
    STREET = os.getenv("STREET")
    HOUSE = os.getenv("HOUSE")

    print("🟦 Параметры автоматизации:")
    print("   Город :", CITY)
    print("   Улица :", STREET)
    print("   Дом   :", HOUSE)
    print()

    URL = "https://www.dtek-dnem.com.ua/ua/shutdowns"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context()
        page = context.new_page()

        print("Открываю страницу...", URL)
        page.goto(URL, wait_until="domcontentloaded", timeout=30000)

        # ---------------------------
        #   Закрыть предупреждение
        # ---------------------------
        try:
            modal_btn = page.locator("button.modal__close.m-attention__close")
            if modal_btn.count() > 0:
                print("Закрываю предупреждение.")
                safe_click(modal_btn.first)
                time.sleep(0.5)
            else:
                alt = page.locator("button[aria-label='close'], button[class*='modal__close']")
                if alt.count() > 0:
                    print("Закрываю альтернативное предупреждение.")
                    safe_click(alt.first)
        except Exception:
            pass

        # ---------------------------
        #   ВВОД ГОРОДА
        # ---------------------------
        print(f"Ввожу город: {CITY}")
        try:
            page.fill("#city", CITY)
            page.wait_for_timeout(600)

            # strong с названием города
            strong_city = page.locator(f"strong:has-text(\"{CITY.split()[-1]}\")")
            if strong_city.count() > 0:
                strong_city.first.click(timeout=5000)
            else:
                # fallback – первый вариант
                sugg = page.locator("ul[role='listbox'] li")
                if sugg.count() > 0:
                    sugg.first.click(timeout=5000)
        except Exception as e:
            print("Ошибка при выборе города:", e)

        # ---------------------------
        #   ВВОД УЛИЦЫ
        # ---------------------------
        print(f"Ввожу улицу: {STREET}")
        try:
            page.fill("#street", STREET)
            page.wait_for_timeout(600)

            strong_street = page.locator(f"strong:has-text(\"{STREET.split()[0]}\")")
            if strong_street.count() > 0:
                strong_street.first.click(timeout=5000)
            else:
                sugg = page.locator("ul[role='listbox'] li")
                if sugg.count() > 0:
                    sugg.first.click(timeout=5000)
        except Exception as e:
            print("Ошибка при выборе улицы:", e)

        # ---------------------------
        #   ВВОД ДОМА
        # ---------------------------
        print(f"Ввожу дом: {HOUSE}")
        try:
            page.fill("#house_num", HOUSE)
            page.wait_for_timeout(500)

            sugg = page.locator("ul[role='listbox'] li")
            if sugg.count() > 0:
                sugg.first.click(timeout=4000)
            else:
                page.press("#house_num", "Enter")
        except Exception as e:
            print("Ошибка при выборе дома:", e)

        # ---------------------------
        #   SUBMIT формы (если есть)
        # ---------------------------
        try:
            submit = page.locator("button[type='submit'], button.search-button, button.btn--search")
            if submit.count() > 0:
                submit.first.click(timeout=3000)
            else:
                page.press("#house_num", "Enter")
        except Exception:
            pass

        # Подождать обновления
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            time.sleep(2)

        # ---------------------------
        #   СОХРАНЕНИЕ HTML
        # ---------------------------
        html = page.content()
        OUTPATH.write_text(html, encoding="utf-8")
        print(f"HTML сохранён в: {OUTPATH}")

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




    print("Готово.")


if __name__ == "__main__":
    main()

