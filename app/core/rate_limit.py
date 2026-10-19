import time
from collections import defaultdict, deque

from app.core.errors import ApiError


class RateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        events = self._events[key]
        while events and events[0] <= now - window_seconds:
            events.popleft()
        if len(events) >= limit:
            raise ApiError(
                429,
                "rate_limited",
                "Demasiados intentos. Intenta de nuevo mas tarde.",
            )
        events.append(now)

    def reset(self) -> None:
        self._events.clear()


rate_limiter = RateLimiter()
