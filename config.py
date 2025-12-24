#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Централизованная конфигурация проекта
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Загрузка .env файла
load_dotenv()

# ======================
# Telegram Bot Settings
# ======================
API_TOKEN = os.getenv("API_TOKEN")
ADMIN_ID_STR = os.getenv("ADMIN_ID")

if not API_TOKEN:
    raise RuntimeError("❌ API_TOKEN не установлен в .env файле")
if not ADMIN_ID_STR:
    raise RuntimeError("❌ ADMIN_ID не установлен в .env файле")

try:
    ADMIN_ID = int(ADMIN_ID_STR)
except ValueError:
    raise RuntimeError("❌ ADMIN_ID должен быть числом")

# ======================
# File Paths
# ======================
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "user.db"
HTML_PATH = BASE_DIR / "dtek_shutdowns.html"
JSON_PATH = BASE_DIR / "today_schedule.json"
PNG_PATH = BASE_DIR / "today_schedule.png"

# ======================
# Automation Settings
# ======================
HEADLESS_BROWSER = True  # False для отладки
BROWSER_TIMEOUT = 30000  # 30 секунд
PARSER_TIMEOUT = 120     # 2 минуты

# ======================
# Cache Settings
# ======================
CACHE_MAX_SIZE = 100
CACHE_TTL_MINUTES = 5

# ======================
# Default URL
# ======================
DEFAULT_DTEK_URL = "https://www.dtek-dnem.com.ua/ua/shutdowns"
