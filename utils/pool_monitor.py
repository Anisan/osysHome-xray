import time
import threading
from dataclasses import dataclass
from typing import List


@dataclass
class PoolStats:
    active_connections: int
    idle_connections: int
    total_connections: int
    pool_size: int
    max_overflow: int
    overflow: int
    timestamp: float
    pool_usage_percent: float
    overflow_usage_percent: float


class DatabasePoolMonitor:
    def __init__(self, engine, logger):
        self.engine = engine
        self.logger = logger
        self.stats_history: List[PoolStats] = []
        self.max_history = 1000
        self._lock = threading.Lock()
        self._monitoring = False

    def get_pool_stats(self) -> PoolStats:
        """Получить текущую статистику пула соединений"""
        pool = self.engine.pool

        # Основные метрики пула
        active = pool.checkedout()
        idle = pool.checkedin()
        total = pool.size()
        overflow = pool.overflow()

        return PoolStats(
            active_connections=active,
            idle_connections=idle,
            total_connections=total,
            pool_size=pool.size(),
            max_overflow=getattr(pool, "_max_overflow", 0),
            overflow=pool.overflow(),
            timestamp=time.time(),
            # Производительность
            pool_usage_percent=round((active / pool.size()) * 100, 2) if pool.size() > 0 else 0,
            overflow_usage_percent=round((overflow / max(getattr(pool, '_max_overflow', 1), 1)) * 100, 2),
        )

    def log_pool_stats(self):
        """Логирование статистики пула"""
        stats = self.get_pool_stats()

        with self._lock:
            self.stats_history.append(stats)
            if len(self.stats_history) > self.max_history:
                self.stats_history.pop(0)

        self.logger.debug(
            f"Pool stats: active={stats.active_connections}, "
            f"idle={stats.idle_connections}, "
            f"total={stats.total_connections}, "
            f"overflow={stats.overflow}"
        )

        # Предупреждения о высокой нагрузке
        usage_percent = (stats.active_connections / stats.pool_size) * 100
        if usage_percent > 80:
            self.logger.warning(
                f"High pool usage: {stats.active_connections}/{stats.pool_size} "
                f"({usage_percent:.1f}%)"
            )
        elif usage_percent > 90:
            self.logger.error(
                f"Critical pool usage: {stats.active_connections}/{stats.pool_size} "
                f"({usage_percent:.1f}%)"
            )

    def get_stats_history(self, minutes: int = 60) -> List[PoolStats]:
        """Получить историю статистики за последние N минут"""
        cutoff_time = time.time() - (minutes * 60)

        with self._lock:
            return [s for s in self.stats_history if s.timestamp > cutoff_time]

    def start_monitoring(self, interval: int = 60):
        """Запуск периодического мониторинга"""
        if self._monitoring:
            return

        self._monitoring = True

        def monitor_loop():
            while self._monitoring:
                try:
                    self.log_pool_stats()
                    time.sleep(interval)
                except Exception as e:
                    self.logger.error(f"Pool monitoring error: {e}")
                    time.sleep(interval)

        monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        monitor_thread.start()
        self.logger.info(f"Pool monitoring started with {interval}s interval")

    def stop_monitoring(self):
        """Остановка мониторинга"""
        self._monitoring = False
        self.logger.info("Pool monitoring stopped")
