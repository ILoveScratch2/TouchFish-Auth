"""登录失败退避。

这是**单进程内存**实现
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

IDLE_TTL = 3600.0


@dataclass
class _Bucket:
    failures: int = 0
    first_at: float = 0.0
    last_at: float = 0.0
    locked_until: float = 0.0


class Throttle:
    def __init__(self, *, window: float = 900.0, free_attempts: int = 8,
                 base_delay: float = 2.0, max_delay: float = 900.0) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[str, _Bucket] = {}
        self.window = window
        self.free_attempts = max(1, free_attempts)
        self.base_delay = base_delay
        self.max_delay = max_delay

    def _expired(self, bucket: _Bucket, now: float) -> bool:
        return now - bucket.last_at > self.window

    def blocked_for(self, *keys: str) -> int:
        """返回还需等待的秒数；0 表示可以继续。"""
        now = time.time()
        longest = 0.0
        with self._lock:
            for key in keys:
                bucket = self._buckets.get(key)
                if bucket is None:
                    continue
                if self._expired(bucket, now) and bucket.locked_until <= now:
                    self._buckets.pop(key, None)
                    continue
                if bucket.locked_until > now:
                    longest = max(longest, bucket.locked_until - now)
        return int(longest) + (1 if longest > 0 else 0)

    def fail(self, *keys: str) -> int:
        """记录一次失败，返回本次触发的锁定时长（0 表示尚未锁定）。"""
        now = time.time()
        delay = 0.0
        with self._lock:
            for key in keys:
                bucket = self._buckets.get(key)
                if bucket is None or self._expired(bucket, now):
                    bucket = _Bucket(first_at=now)
                    self._buckets[key] = bucket
                bucket.failures += 1
                bucket.last_at = now
                if bucket.failures >= self.free_attempts:
                    over = bucket.failures - self.free_attempts
                    delay = min(self.base_delay * (2 ** over), self.max_delay)
                    bucket.locked_until = max(bucket.locked_until, now + delay)
        return int(delay)

    def reset(self, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._buckets.pop(key, None)

    def reset_all(self) -> None:
        """仅测试用：清空所有计数。生产不该调用。"""
        with self._lock:
            self._buckets.clear()

    def prune(self) -> int:
        """回收长期闲置的桶，避免字典无限增长。"""
        now = time.time()
        with self._lock:
            stale = [
                key for key, bucket in self._buckets.items()
                if now - max(bucket.last_at, bucket.locked_until) > IDLE_TTL
            ]
            for key in stale:
                self._buckets.pop(key, None)
        return len(stale)

    def size(self) -> int:
        with self._lock:
            return len(self._buckets)


_THROTTLE = Throttle()


def get() -> Throttle:
    return _THROTTLE


def configure(free_attempts: int) -> None:
    """按站点配置调整阈值（管理员可改，无需重启）。"""
    _THROTTLE.free_attempts = max(1, int(free_attempts))
