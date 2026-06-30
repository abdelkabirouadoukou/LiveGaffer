"""
A minimal async sliding-window rate limiter.

Used by `api_football_client.py` to stay under RapidAPI's free-tier
burst limits (e.g. ~10 requests/minute) without needing an external
dependency like `aiolimiter`.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque


class AsyncRateLimiter:
    """
    Sliding-window rate limiter: allows at most `max_calls` within any
    rolling `period_seconds` window. Safe for concurrent coroutines.

    Example:
        limiter = AsyncRateLimiter(max_calls=8, period_seconds=60)
        async with limiter:
            await client.get(...)
    """

    def __init__(self, max_calls: int, period_seconds: float) -> None:
        if max_calls <= 0:
            raise ValueError("max_calls must be positive")
        if period_seconds <= 0:
            raise ValueError("period_seconds must be positive")

        self._max_calls = max_calls
        self._period_seconds = period_seconds
        self._call_timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            # Drop timestamps that have aged out of the window
            while (
                self._call_timestamps
                and now - self._call_timestamps[0] > self._period_seconds
            ):
                self._call_timestamps.popleft()

            if len(self._call_timestamps) >= self._max_calls:
                oldest = self._call_timestamps[0]
                wait_time = self._period_seconds - (now - oldest)
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                # Re-evaluate the window after sleeping
                now = time.monotonic()
                while (
                    self._call_timestamps
                    and now - self._call_timestamps[0] > self._period_seconds
                ):
                    self._call_timestamps.popleft()

            self._call_timestamps.append(time.monotonic())

    async def __aenter__(self) -> "AsyncRateLimiter":
        await self.acquire()
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        return None
