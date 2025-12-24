#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Persistent кэш с сохранением на диск
"""

import json
import hashlib
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List

import config


class PersistentScheduleCache:
    """
    Улучшенный кэш с:
    - Сохранением на диск (сохраняется между перезапусками)
    - Автоматической очисткой устаревших записей
    - Статистикой (hits/misses)
    """

    def __init__(
        self,
        max_size: int = 100,
        ttl_minutes: int = 5,
        cache_file: Path = None
    ):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.max_size = max_size
        self.ttl = timedelta(minutes=ttl_minutes)
        self.cache_file = cache_file or config.BASE_DIR / "schedule_cache.pkl"

        # Статистика
        self.hits = 0
        self.misses = 0

        # Загрузить кэш при инициализации
        self._load_from_disk()

    def _make_key(
        self,
        city: str,
        street: str,
        house: str,
        url: str,
        next_day: bool = False
    ) -> str:
        """Создание уникального ключа"""
        key_data = f"{city}|{street}|{house}|{url}|{next_day}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def _is_expired(self, entry: Dict[str, Any]) -> bool:
        """Проверка истечения срока"""
        return datetime.now() - entry['timestamp'] > self.ttl

    def _cleanup_expired(self):
        """Удаление устаревших записей"""
        expired_keys = [
            key for key, entry in self.cache.items()
            if self._is_expired(entry)
        ]
        for key in expired_keys:
            del self.cache[key]

    def _evict_if_needed(self):
        """Удаление старейшей записи если кэш переполнен"""
        if len(self.cache) >= self.max_size:
            oldest_key = min(
                self.cache.keys(),
                key=lambda k: self.cache[k]['timestamp']
            )
            del self.cache[oldest_key]

    def _load_from_disk(self):
        """Загрузка кэша из файла"""
        if not self.cache_file.exists():
            return

        try:
            with open(self.cache_file, 'rb') as f:
                data = pickle.load(f)
                self.cache = data.get('cache', {})
                self.hits = data.get('hits', 0)
                self.misses = data.get('misses', 0)

            # Очистка устаревших записей
            self._cleanup_expired()

            print(f"💾 Загружен кэш: {len(self.cache)} записей")

        except Exception as e:
            print(f"⚠️ Ошибка загрузки кэша: {e}")
            self.cache = {}

    def _save_to_disk(self):
        """Сохранение кэша на диск"""
        try:
            data = {
                'cache': self.cache,
                'hits': self.hits,
                'misses': self.misses,
                'saved_at': datetime.now()
            }

            with open(self.cache_file, 'wb') as f:
                pickle.dump(data, f)

        except Exception as e:
            print(f"⚠️ Ошибка сохранения кэша: {e}")

    def get(
        self,
        city: str,
        street: str,
        house: str,
        url: str,
        next_day: bool = False
    ) -> Optional[List[Dict[str, str]]]:
        """
        Получить график из кэша

        Returns:
            Schedule или None
        """
        key = self._make_key(city, street, house, url, next_day)

        if key not in self.cache:
            self.misses += 1
            return None

        entry = self.cache[key]

        # Проверка срока действия
        if self._is_expired(entry):
            del self.cache[key]
            self.misses += 1
            return None

        self.hits += 1
        entry['last_accessed'] = datetime.now()

        return entry['schedule']

    def set(
        self,
        city: str,
        street: str,
        house: str,
        url: str,
        schedule: List[Dict[str, str]],
        next_day: bool = False
    ):
        """
        Сохранить график в кэш
        """
        key = self._make_key(city, street, house, url, next_day)

        # Очистка и проверка размера
        self._cleanup_expired()
        self._evict_if_needed()

        # Сохранение
        self.cache[key] = {
            'schedule': schedule,
            'timestamp': datetime.now(),
            'last_accessed': datetime.now(),
            'city': city,
            'street': street,
            'house': house,
            'next_day': next_day
        }

        # Сохранить на диск
        self._save_to_disk()

    def clear(self):
        """Очистка всего кэша"""
        self.cache.clear()
        self.hits = 0
        self.misses = 0
        self._save_to_disk()

    def get_stats(self) -> Dict[str, Any]:
        """Статистика кэша"""
        self._cleanup_expired()

        total_requests = self.hits + self.misses
        hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0

        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'ttl_minutes': self.ttl.total_seconds() / 60,
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': round(hit_rate, 2),
            'cache_file': str(self.cache_file)
        }

    def get_popular_addresses(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Получить топ популярных адресов"""
        entries = []

        for key, entry in self.cache.items():
            if not self._is_expired(entry):
                entries.append({
                    'city': entry.get('city', '?'),
                    'street': entry.get('street', '?'),
                    'house': entry.get('house', '?'),
                    'last_accessed': entry.get('last_accessed'),
                })

        # Сортировка по последнему доступу
        entries.sort(key=lambda x: x['last_accessed'], reverse=True)

        return entries[:limit]


# Глобальный экземпляр
schedule_cache = PersistentScheduleCache(
    max_size=config.CACHE_MAX_SIZE,
    ttl_minutes=config.CACHE_TTL_MINUTES
)
