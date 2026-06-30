"""
Minimal in-memory TTL cache.

Both `live_match_service.py` and `analysis_service.py` use this to avoid
hammering the API-Football free tier (100 req/day) and the LLM providers'
free quotas on every Streamlit rerun / API poll. It is intentionally
single-process and in-memory — no Redis, no external dependency — which is
all this app needs at this stage (a Streamlit dev server or a single
FastAPI worker). Swapping in a real cache backend later only touches this
file; nothing in `services` or above needs to change.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from src.utils.logger import get_logger

log = get_logger(__name__)

T = TypeVar("T")


@dataclass
class _CacheEntry(Generic[T]):
    value: T
    expires_at: float


class TTLCache:
    """
    Async-safe, string-keyed TTL cache.

    Usage:
        cache = TTLCache(default_ttl_seconds=45)
        value = await cache.get_or_set("key", lambda: expensive_coro())
    """

    def __init__(self, default_ttl_seconds: float = 45.0) -> None:
        if default_ttl_seconds < 0:
            raise ValueError("default_ttl_seconds must be >= 0")
        self._default_ttl = default_ttl_seconds
        self._store: dict[str, _CacheEntry[Any]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        """Return the cached value for `key`, or None if missing/expired."""
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if time.monotonic() >= entry.expires_at:
                del self._store[key]
                return None
            return entry.value

    async def set(self, key: str, value: Any, ttl_seconds: float | None = None) -> None:
        ttl = self._default_ttl if ttl_seconds is None else ttl_seconds
        async with self._lock:
            self._store[key] = _CacheEntry(value=value, expires_at=time.monotonic() + ttl)

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Awaitable[T]],
        ttl_seconds: float | None = None,
    ) -> T:
        """
        Return the cached value for `key` if still fresh; otherwise await
        `factory()`, cache its result, and return it.

        Note: deliberately not lock-guarded across the factory call itself —
        a brief duplicate fetch on a cold cache (e.g. two near-simultaneous
        Streamlit reruns) is cheap and far simpler than a stampede-proof
        cache, which this small app doesn't need.
        """
        cached = await self.get(key)
        if cached is not None:
            log.debug("Cache HIT: {}", key)
            return cached

        log.debug("Cache MISS: {}", key)
        value = await factory()
        await self.set(key, value, ttl_seconds=ttl_seconds)
        return value

    async def invalidate(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()

    async def size(self) -> int:
        async with self._lock:
            return len(self._store)