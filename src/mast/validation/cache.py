"""LRU + TTL cache for validation results."""

from __future__ import annotations

import time
from collections import OrderedDict


class ValidationCache[T]:
    """Simple in-memory LRU cache with TTL expiry."""

    def __init__(self, ttl_seconds: int = 300, max_size: int = 256) -> None:
        """Initialize validation cache with TTL and max size."""
        self._ttl = ttl_seconds
        self._max = max_size
        self._store: OrderedDict[str, tuple[float, T]] = OrderedDict()

    def get(self, key: str) -> T | None:
        if key not in self._store:
            return None
        ts, value = self._store[key]
        if time.monotonic() - ts > self._ttl:
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: T) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (time.monotonic(), value)
        if len(self._store) > self._max:
            self._store.popitem(last=False)  # evict oldest
