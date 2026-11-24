import asyncio
import math
import time
from collections import deque

from fastapi import Request

RATE_LIMIT_REQUESTS = 5
RATE_LIMIT_WINDOW_SECONDS = 60


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int):
        super().__init__("Rate limit exceeded")
        self.retry_after = retry_after


class SlidingWindowRateLimiter:
    def __init__(
        self,
        max_requests: int = RATE_LIMIT_REQUESTS,
        window_seconds: int = RATE_LIMIT_WINDOW_SECONDS,
    ):
        if max_requests < 1 or window_seconds < 1:
            raise ValueError("Rate limit and window must be positive")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()
        self._next_cleanup = 0.0

    async def check(self, key: str) -> int | None:
        now = time.monotonic()
        cutoff = now - self.window_seconds

        async with self._lock:
            if now >= self._next_cleanup:
                expired = []
                for existing_key, timestamps in self._requests.items():
                    while timestamps and timestamps[0] <= cutoff:
                        timestamps.popleft()
                    if not timestamps:
                        expired.append(existing_key)
                for existing_key in expired:
                    del self._requests[existing_key]
                self._next_cleanup = now + self.window_seconds

            timestamps = self._requests.setdefault(key, deque())
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()

            if len(timestamps) >= self.max_requests:
                return max(1, math.ceil(self.window_seconds - (now - timestamps[0])))

            timestamps.append(now)
            return None


async def enforce_rate_limit(request: Request, user_id: str, operation: str) -> None:
    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        raise RuntimeError("Gateway rate limiter was not initialized")
    retry_after = await limiter.check(f"{operation}:{user_id}")
    if retry_after is not None:
        raise RateLimitExceeded(retry_after)
