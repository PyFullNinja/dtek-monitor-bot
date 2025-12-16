#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Оптимизированный парсер графика отключений DTEK
"""

import sys
import json
from pathlib import Path
from typing import List, Dict, Set
from bs4 import BeautifulSoup, Tag

# Константы статусов
OFF_CLASSES: Set[str] = {
    "cell-scheduled",
    "cell-scheduled-maybe",
    "cell-scheduled-maybe ",
}
ON_CLASSES: Set[str] = {"cell-non-scheduled"}
FIRST_HALF = "cell-first-half"
SECOND_HALF = "cell-second-half"

JSON_OUTPUT = Path("today_schedule.json")


def find_active_table(soup: BeautifulSoup) -> Tag:
    """Поиск активной таблицы с графиком"""
    table = soup.select_one("div.discon-fact-table.active table") or soup.select_one(
        "div.discon-fact-table table"
    )

    if not table:
        raise RuntimeError("Не удалось найти таблицу discon-fact-table в HTML")

    return table


def extract_headers(table: Tag) -> List[str]:
    """Извлечение заголовков часов из таблицы"""
    headers = [th.get_text(strip=True) for th in table.select("thead th[scope='col']")]

    if not headers:
        headers = [div.get_text(strip=True) for div in table.select("thead th div")]

    return headers


def find_current_day_row(table: Tag) -> Tag:
    """Поиск строки с текущим днём"""
    for tr in table.select("tbody tr"):
        if tr.find("td", class_="current-day") or "current-day" in (
            tr.get("class") or []
        ):
            return tr

    # Fallback: последняя строка
    rows = table.select("tbody tr")
    if not rows:
        raise RuntimeError("Не удалось найти строку с сегодняшним днём")

    return rows[-1]


def determine_status(classes: Set[str]) -> str:
    """Определение статуса по CSS классам"""
    if classes & ON_CLASSES:
        return "on"

    if classes & OFF_CLASSES:
        return "off"

    # Проверка по подстрокам
    cls_str = " ".join(classes)

    if "non-sched" in cls_str:
        return "on"

    if "schedul" in cls_str:
        return "off"

    return "unknown"


def parse_cell(cell: Tag, hour: int) -> List[Dict[str, str]]:
    """Парсинг одной ячейки таблицы (час)"""
    classes = set(cell.get("class") or [])

    # Формирование временных интервалов
    next_hour = (hour + 1) % 24
    half1 = f"{hour:02d}:00-{hour:02d}:30"
    half2 = f"{hour:02d}:30-{next_hour:02d}:00"

    # Обработка специальных классов (половины часа)
    if FIRST_HALF in classes:
        return [
            {"interval": half1, "status": "off"},
            {"interval": half2, "status": "on"},
        ]

    if SECOND_HALF in classes:
        return [
            {"interval": half1, "status": "on"},
            {"interval": half2, "status": "off"},
        ]

    # Обработка полного часа
    status = determine_status(classes)
    return [
        {"interval": half1, "status": status},
        {"interval": half2, "status": status},
    ]


def parse_file(path: str) -> List[Dict[str, str]]:
    """Основная функция парсинга HTML файла"""
    html = Path(path).read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "lxml")

    # Поиск таблицы и строки
    table = find_active_table(soup)
    headers = extract_headers(table)
    current_row = find_current_day_row(table)

    # Извлечение ячеек, учитывая служебные колонки в начале строки
    cells = current_row.find_all("td")
    extra_cells = max(0, len(cells) - len(headers))
    cells = cells[extra_cells:]

    # Согласование количества ячеек и заголовков
    min_len = min(len(cells), len(headers))
    cells = cells[:min_len]
    headers = headers[:min_len]

    # Парсинг каждой ячейки
    schedule = []
    for i, header in enumerate(headers):
        # Извлечение часа из заголовка (например, "00-01" -> 1)
        try:
            hour = int(header.split("-")[0])
        except (ValueError, IndexError):
            hour = i

        cell = cells[i] if i < len(cells) else None
        if cell:
            schedule.extend(parse_cell(cell, hour))

    return schedule


def save_schedule(schedule: List[Dict[str, str]], output: Path = JSON_OUTPUT) -> None:
    """Сохранение графика в JSON файл"""
    output.write_text(
        json.dumps(schedule, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"✅ График сохранён в {output}")


def main():
    if len(sys.argv) < 2:
        print("❌ Укажите путь к HTML-файлу")
        print("Пример: python main.py dtek_shutdowns.html")
        sys.exit(1)

    path = sys.argv[1]

    try:
        schedule = parse_file(path)
        save_schedule(schedule)
    except Exception as e:
        print(f"❌ Ошибка парсинга: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
