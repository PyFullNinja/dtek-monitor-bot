#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Асинхронный сервис парсинга с очередью задач
"""

import asyncio
import uuid
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

from dtek_automate import DTEKAutomation
import config


class TaskStatus(Enum):
    """Статусы задач парсинга"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ParsingTask:
    """Задача парсинга"""
    task_id: str
    city: str
    street: str
    house: str
    url: str
    next_day: bool
    status: TaskStatus
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: datetime = None
    updated_at: datetime = None
    progress: str = "Создана задача"

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()


class ParserService:
    """
    Асинхронный сервис для парсинга графиков DTEK

    Особенности:
    - Парсинг в отдельном процессе (не блокирует бота)
    - Очередь задач с приоритетами
    - Обновления прогресса в реальном времени
    - Retry механизм (3 попытки)
    """

    def __init__(self, max_workers: int = 3):
        self.tasks: Dict[str, ParsingTask] = {}
        self.queue = asyncio.Queue()
        self.max_workers = max_workers
        self.workers = []
        self.callbacks: Dict[str, Callable] = {}

    async def start(self):
        """Запуск worker-процессов"""
        print(f"🚀 Запуск {self.max_workers} парсинг-воркеров")
        self.workers = [
            asyncio.create_task(self._worker(i))
            for i in range(self.max_workers)
        ]

    async def stop(self):
        """Остановка всех воркеров"""
        print("🛑 Остановка парсинг-воркеров")
        for worker in self.workers:
            worker.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)

    async def submit_task(
        self,
        city: str,
        street: str,
        house: str,
        url: str,
        next_day: bool = False,
        callback: Optional[Callable] = None
    ) -> str:
        """
        Отправить задачу в очередь

        Returns:
            task_id - уникальный идентификатор задачи
        """
        task_id = str(uuid.uuid4())[:8]

        task = ParsingTask(
            task_id=task_id,
            city=city,
            street=street,
            house=house,
            url=url,
            next_day=next_day,
            status=TaskStatus.PENDING
        )

        self.tasks[task_id] = task

        if callback:
            self.callbacks[task_id] = callback

        await self.queue.put(task_id)

        print(f"📝 Задача {task_id} добавлена в очередь")
        return task_id

    def get_task_status(self, task_id: str) -> Optional[ParsingTask]:
        """Получить статус задачи"""
        return self.tasks.get(task_id)

    async def _worker(self, worker_id: int):
        """Worker для обработки задач из очереди"""
        print(f"👷 Worker {worker_id} запущен")

        while True:
            try:
                # Берём задачу из очереди
                task_id = await self.queue.get()
                task = self.tasks.get(task_id)

                if not task:
                    continue

                print(f"🔧 Worker {worker_id} обрабатывает задачу {task_id}")
                task.status = TaskStatus.RUNNING
                task.updated_at = datetime.now()

                # Выполняем парсинг с retry
                success = await self._parse_with_retry(task, worker_id)

                if success:
                    task.status = TaskStatus.COMPLETED
                    task.progress = "✅ Готово"
                else:
                    task.status = TaskStatus.FAILED
                    task.progress = "❌ Ошибка"

                task.updated_at = datetime.now()

                # Вызываем callback если есть
                if task_id in self.callbacks:
                    callback = self.callbacks[task_id]
                    await callback(task)
                    del self.callbacks[task_id]

                self.queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"❌ Ошибка в worker {worker_id}: {e}")

    async def _parse_with_retry(
        self,
        task: ParsingTask,
        worker_id: int,
        max_attempts: int = 3
    ) -> bool:
        """Парсинг с повторными попытками"""

        for attempt in range(1, max_attempts + 1):
            try:
                task.progress = f"🔄 Попытка {attempt}/{max_attempts}"
                task.updated_at = datetime.now()

                # Запускаем парсинг в отдельном потоке
                result = await asyncio.to_thread(
                    self._run_automation,
                    task,
                    worker_id
                )

                if result:
                    task.result = result
                    return True

            except Exception as e:
                task.error = str(e)
                print(f"⚠️ Попытка {attempt} не удалась: {e}")

                if attempt < max_attempts:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff

        return False

    def _run_automation(self, task: ParsingTask, worker_id: int) -> bool:
        """
        Запуск автоматизации (синхронная функция для to_thread)
        """
        try:
            print(f"🌐 Worker {worker_id} запускает Playwright для {task.task_id}")

            automation = DTEKAutomation(
                task.city,
                task.street,
                task.house,
                task.url,
                task.next_day
            )

            task.progress = "🌐 Открываю сайт..."
            success = automation.run()

            if success:
                task.progress = "✅ Данные получены"

            return success

        except Exception as e:
            print(f"❌ Ошибка автоматизации: {e}")
            task.error = str(e)
            return False

    def get_queue_size(self) -> int:
        """Размер очереди"""
        return self.queue.qsize()

    def get_active_tasks_count(self) -> int:
        """Количество активных задач"""
        return sum(
            1 for task in self.tasks.values()
            if task.status == TaskStatus.RUNNING
        )

    def get_stats(self) -> Dict[str, Any]:
        """Статистика сервиса"""
        return {
            "queue_size": self.get_queue_size(),
            "active_tasks": self.get_active_tasks_count(),
            "total_tasks": len(self.tasks),
            "workers": self.max_workers,
            "completed": sum(1 for t in self.tasks.values() if t.status == TaskStatus.COMPLETED),
            "failed": sum(1 for t in self.tasks.values() if t.status == TaskStatus.FAILED),
        }


# Глобальный экземпляр сервиса
parser_service = ParserService(max_workers=2)
