#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Парсер графика отключений "на сегодня" из локального HTML (DTEK).
Запуск:
    python parse_discon.py "/path/to/Планові і аварійні відключення _ Офіційний сайт ДТЕК.html"
"""

import sys
from bs4 import BeautifulSoup
from pathlib import Path
import json
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

# ---------- настройки статусов ----------
OFF_CLASSES = {"cell-scheduled", "cell-scheduled-maybe", "cell-scheduled-maybe "}
ON_CLASSES = {"cell-non-scheduled"}
FIRST_HALF = "cell-first-half"
SECOND_HALF = "cell-second-half"
# ----------------------------------------


def parse_file(path):
    html = Path(path).read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "lxml")

    # Найти таблицу с классом discon-fact-table и активную (есть несколько)
    table = soup.select_one("div.discon-fact-table.active table") or soup.select_one(
        "div.discon-fact-table table"
    )
    if not table:
        raise RuntimeError("Не удалось найти таблицу discon-fact-table в HTML.")

    # Заголовки часов (scope="col")
    headers = [th.get_text(strip=True) for th in table.select("thead th[scope='col']")]
    if not headers:
        # иногда заголовки внутри <th><div>...
        headers = [div.get_text(strip=True) for div in table.select("thead th div")]

    # Найти строку, помеченную как current-day
    selected_row = None
    for tr in table.select("tbody tr"):
        # td с class="current-day" или сам tr с классом
        if tr.find("td", class_="current-day") or (
            "current-day" in (tr.get("class") or [])
        ):
            selected_row = tr
            break
    if selected_row is None:
        # fallback: ищем td, содержащую слово 'на сьогодні' или 'Неділя' и т.п.
        # Но не запрашиваем у пользователя — берем первую строку с colspan=2 и class current-day отсутствует
        # попытаемся найти row с <td class="current-day"> внутри (повторно), иначе берем последнюю
        rows = table.select("tbody tr")
        if rows:
            selected_row = rows[-1]
        else:
            raise RuntimeError("Не удалось найти строку с сегодняшним днём в таблице.")

    # Каждая строка: первые 2 td — название дня, дальше — колонки часов
    tds = selected_row.find_all("td")
    cells = tds[2:]  # от третьей ячейки — статусы по часам
    if len(cells) != len(headers):
        # иногда есть пробельные/пустые ячейки — подрезаем / дополняем
        n = min(len(cells), len(headers))
        cells = cells[:n]
        headers = headers[:n]

    schedule = []  # список словарей {"interval": "HH:MM-HH:MM", "status": "on/off/unknown"}
    for i, header in enumerate(headers):
        # header example "00-01" -> start_hour = 0
        # безопасно парсим первые два числа
        try:
            hh = int(header.split("-")[0]) + 1
        except Exception:
            hh = i  # fallback
        # формируем два получасовых интервала
        half1 = f"{hh:02d}:00-{hh:02d}:30"
        next_h = (hh + 1) % 24
        half2 = f"{hh:02d}:30-{next_h:02d}:00"

        cell = cells[i] if i < len(cells) else None
        classes = set(cell.get("class") or []) if cell else set()

        # определить статус
        if classes & ON_CLASSES:
            # оба получасовых окна — on
            schedule.append({"interval": half1, "status": "on"})
            schedule.append({"interval": half2, "status": "on"})
        elif classes & OFF_CLASSES:
            schedule.append({"interval": half1, "status": "off"})
            schedule.append({"interval": half2, "status": "off"})
        elif FIRST_HALF in classes:
            schedule.append({"interval": half1, "status": "off"})
            schedule.append({"interval": half2, "status": "on"})
        elif SECOND_HALF in classes:
            schedule.append({"interval": half1, "status": "on"})
            schedule.append({"interval": half2, "status": "off"})
        else:
            # возможно класс cell-scheduled (без maybe) или другие варианты
            # попробуем искать substrings
            cls_str = " ".join(classes)
            if "non-sched" in cls_str:
                schedule.append({"interval": half1, "status": "on"})
                schedule.append({"interval": half2, "status": "on"})
            elif "schedul" in cls_str:
                schedule.append({"interval": half1, "status": "off"})
                schedule.append({"interval": half2, "status": "off"})
            else:
                schedule.append({"interval": half1, "status": "unknown"})
                schedule.append({"interval": half2, "status": "unknown"})

    return schedule


def print_schedule(schedule):
    print("График на сегодня (полчасовые интервалы):")
    for item in schedule:
        print(f"{item['interval']:13} -> {item['status']}")


def plot_schedule(schedule, out_png="today_schedule.png"):
    # преобразуем в числа для построения: x = минут с 00:00
    starts = []
    vals = []  # 1 on, 0 off, 0.5 maybe/partial, -1 unknown
    for it in schedule:
        start_str = it["interval"].split("-")[0]
        hh, mm = map(int, start_str.split(":"))
        mins = hh * 60 + mm
        starts.append(mins)
        s = it["status"]
        if s == "on":
            vals.append(1.0)
        elif s == "off":
            vals.append(0.0)
        elif s in ("first-half", "second-half", "maybe"):
            vals.append(0.5)
        else:
            vals.append(-0.1)

    # рисуем полосу времени
    fig, ax = plt.subplots(figsize=(12, 2))
    heights = [1] * len(starts)
    # цвета по статусу (можно менять)
    colors = []
    for v in vals:
        if v == 1.0:
            colors.append("green")
        elif v == 0.0:
            colors.append("red")
        elif v == 0.5:
            colors.append("orange")
        else:
            colors.append("gray")

    ax.barh(0, 30, left=starts, height=0.6, color=colors, edgecolor="black")
    ax.set_xlim(0, 24 * 60)
    ax.set_ylim(-1, 1)
    ax.set_yticks([])
    ax.set_xlabel("Время (минуты с 00:00)")
    ax.set_title("График отключений на сегодня (полчасовые интервалы)")
    # подписи через каждые 2 часа
    xticks = [i * 60 for i in range(0, 25, 2)]
    ax.set_xticks(xticks)
    ax.set_xticklabels([f"{t // 60:02d}:00" for t in xticks])
    # легенда
    from matplotlib.patches import Patch

    legend_elems = [
        Patch(facecolor="green", edgecolor="k", label="Світло є"),
        Patch(facecolor="red", edgecolor="k", label="Світла немає"),
        Patch(facecolor="orange", edgecolor="k", label="Можливо / половина"),
        Patch(facecolor="gray", edgecolor="k", label="Неизвестно"),
    ]
    ax.legend(handles=legend_elems, bbox_to_anchor=(1.01, 1), loc="upper left")
    plt.tight_layout()
    fig.savefig(out_png)
    print(f"График сохранён в {out_png}")


def main():
    if len(sys.argv) < 2:
        print("Укажите путь к HTML-файлу. Пример:")
        print(
            '  python parse_discon.py "/mnt/data/Планові і аварійні відключення _ Офіційний сайт ДТЕК.html"'
        )
        sys.exit(1)
    path = sys.argv[1]
    schedule = parse_file(path)
    # print_schedule(schedule)
    # сохранить JSON
    json_out = Path("today_schedule.json")
    json_out.write_text(
        json.dumps(schedule, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Сохранено в {json_out}")
    # нарисовать график (при наличии matplotlib)
    # try:
    #    plot_schedule(schedule, out_png="today_schedule.png")
    # except Exception as e:
    #    print("Не удалось построить график (matplotlib):", e)


if __name__ == "__main__":
    main()
