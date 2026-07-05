import asyncio
from datetime import datetime
import aiohttp
import random
import hashlib
from collections import deque
import threading
import time
import sys
import os

from constants import ANU_API_URL, logger
CACHE_SIZE = 500
PRELOAD_TRESHOLD = 0.3

# ===== КЕШИРУЕМЫЙ КВАНТОВЫЙ ГЕНЕРАТОР =====
class CachedQuantumGenerator:
    """Генератор с кешированием квантовых чисел."""
    
    def __init__(self, cache_size: int = CACHE_SIZE, preload_threshold: float = PRELOAD_TRESHOLD):
        self.cache_size = cache_size
        self.preload_threshold = preload_threshold
        self._cache: deque = deque(maxlen=cache_size)
        self._lock = threading.Lock()
        self._session: aiohttp.ClientSession | None = None
        self._background_task: asyncio.Task | None = None
        
        # Статистика
        self.stats = {
            "quantum_used": 0,
            "fallback_used": 0,
            "api_calls": 0,
            "cache_hits": 0,
            "last_refill": None,
            "quantum_available": True
        }
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            connector = aiohttp.TCPConnector(force_close=True)
            self._session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        return self._session
    
    async def _fetch_quantum_bytes(self, count: int) -> list[int] | None:
        """Получение пакета квантовых байтов от ANU API."""
        try:
            session = await self._get_session()
            url = ANU_API_URL.format(length=min(count, 100))
            
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("success") and data.get("data"):
                        bytes_list = [int(b) for b in data["data"]]
                        self.stats["api_calls"] += 1
                        logger.info(f"✅ Получено {len(bytes_list)} квантовых байтов")
                        return bytes_list
                return None
        except Exception as e:
            logger.warning(f"⚠️ Ошибка API: {e}")
            return None
    
    def _generate_fallback_bytes(self, count: int) -> list[int]:
        """Генерация резервных байтов."""
        fallback_bytes = []
        for _ in range(count):
            entropy = (
                str(time.time_ns()) +
                str(random.SystemRandom().random()) +
                str(id(object()))
            )
            hash_byte = hashlib.sha256(entropy.encode()).digest()[0]
            fallback_bytes.append(hash_byte)
        self.stats["fallback_used"] += count
        return fallback_bytes
    
    async def _refill_cache(self) -> None:
        """Пополнение кеша."""
        with self._lock:
            needed = self.cache_size - len(self._cache)
            batch_size = min(needed, 100)
        
        if batch_size <= 0:
            return
        
        quantum_bytes = await self._fetch_quantum_bytes(batch_size)
        
        if quantum_bytes:
            with self._lock:
                self._cache.extend(quantum_bytes)
                self.stats["last_refill"] = datetime.now()
                self.stats["quantum_available"] = True
        else:
            fallback_bytes = self._generate_fallback_bytes(min(batch_size, 20))
            with self._lock:
                self._cache.extend(fallback_bytes)
                self.stats["quantum_available"] = False
    
    async def _background_cache_manager(self) -> None:
        """Фоновый менеджер кеша."""
        while True:
            try:
                await asyncio.sleep(30)
                with self._lock:
                    current_size = len(self._cache)
                    threshold = int(self.cache_size * self.preload_threshold)
                
                if current_size < threshold:
                    await self._refill_cache()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Ошибка менеджера: {e}")
                await asyncio.sleep(60)
    
    async def initialize_cache(self) -> None:
        """Инициализация кеша."""
        logger.info("🚀 Инициализация квантового кеша...")
        
        quantum_bytes = await self._fetch_quantum_bytes(50)
        
        if quantum_bytes:
            with self._lock:
                self._cache.extend(quantum_bytes)
                self.stats["last_refill"] = datetime.now()
            logger.info(f"✅ Кеш заполнен: {len(self._cache)} байтов")
        else:
            fallback_bytes = self._generate_fallback_bytes(50)
            with self._lock:
                self._cache.extend(fallback_bytes)
            logger.info(f"⚠️ Кеш: {len(self._cache)} резервных байтов")
        
        self._background_task = asyncio.create_task(self._background_cache_manager())
    
    def _get_byte_from_cache(self) -> int | None:
        """Извлечение байта из кеша."""
        with self._lock:
            if self._cache:
                return self._cache.popleft()
            return None
    
    async def get_random_number(self, min_val: int, max_val: int) -> tuple[int, bool]:
        """Получение случайного числа."""
        if min_val >= max_val:
            return min_val, True
        
        range_size = max_val - min_val + 1
        
        quantum_byte = self._get_byte_from_cache()
        
        if quantum_byte is not None:
            self.stats["cache_hits"] += 1
            self.stats["quantum_used"] += 1
            return min_val + (quantum_byte % range_size), True
        
        # Экстренное пополнение
        emergency_bytes = await self._fetch_quantum_bytes(10)
        
        if emergency_bytes:
            with self._lock:
                self._cache.extend(emergency_bytes)
            byte = self._get_byte_from_cache()
            if byte is not None:
                self.stats["quantum_used"] += 1
                return min_val + (byte % range_size), True
        
        # Fallback
        fallback_byte = self._generate_fallback_bytes(1)[0]
        return min_val + (fallback_byte % range_size), False
    
    def get_cache_stats(self) -> dict:
        """Статистика кеша."""
        with self._lock:
            cache_len = len(self._cache)
            return {
                "cache_size": cache_len,
                "max_cache": self.cache_size,
                "fill_percentage": (cache_len / self.cache_size) * 100 if self.cache_size > 0 else 0,
                **self.stats
            }
    
    async def close(self):
        """Закрытие генератора и всех ресурсов."""
        try:
            # Отменяем все фоновые задачи
            if hasattr(self, '_background_tasks'):
                for task in self._background_tasks:
                    if not task.done():
                        task.cancel()
            
                # Ждём завершения
                if self._background_tasks:
                    await asyncio.gather(*self._background_tasks, return_exceptions=True)
        
            # Закрываем aiohttp session
            if hasattr(self, 'session') and self.session:
                await self.session.close()
            
        except Exception as e:
            logger.warning(f"Ошибка при закрытии генератора: {e}")