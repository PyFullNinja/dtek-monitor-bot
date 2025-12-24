#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Система логирования для проекта
"""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from datetime import datetime

import config


class ColoredFormatter(logging.Formatter):
    """Цветной форматтер для консоли"""

    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
    }
    RESET = '\033[0m'

    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)


def setup_logger(name: str = "dtek_bot") -> logging.Logger:
    """
    Настройка логгера с:
    - Цветным выводом в консоль
    - Записью в файл с ротацией
    - Разными уровнями для консоли и файла
    """

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Удаляем существующие хэндлеры
    logger.handlers.clear()

    # === Консольный хэндлер ===
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    console_format = ColoredFormatter(
        '%(levelname)s | %(message)s'
    )
    console_handler.setFormatter(console_format)

    # === Файловый хэндлер ===
    log_dir = config.BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / f"bot_{datetime.now().strftime('%Y-%m-%d')}.log"

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)

    file_format = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_format)

    # Добавляем хэндлеры
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


# Глобальный логгер
logger = setup_logger()


# Хелперы для быстрого логирования
def log_info(message: str, **kwargs):
    """Логирование INFO"""
    extra = " | ".join(f"{k}={v}" for k, v in kwargs.items())
    full_message = f"{message} | {extra}" if extra else message
    logger.info(full_message)


def log_error(message: str, error: Exception = None, **kwargs):
    """Логирование ERROR"""
    extra = " | ".join(f"{k}={v}" for k, v in kwargs.items())
    full_message = f"{message} | {extra}" if extra else message

    if error:
        full_message += f" | Error: {str(error)}"

    logger.error(full_message, exc_info=error is not None)


def log_warning(message: str, **kwargs):
    """Логирование WARNING"""
    extra = " | ".join(f"{k}={v}" for k, v in kwargs.items())
    full_message = f"{message} | {extra}" if extra else message
    logger.warning(full_message)


def log_debug(message: str, **kwargs):
    """Логирование DEBUG"""
    extra = " | ".join(f"{k}={v}" for k, v in kwargs.items())
    full_message = f"{message} | {extra}" if extra else message
    logger.debug(full_message)


# Пример использования:
# from logger import log_info, log_error
#
# log_info("Бот запущен", user_id=12345)
# log_error("Не удалось загрузить график", error=e, city="Днепр")
