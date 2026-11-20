"""In-memory sliding-window limit for failed sign-ins.

It is per process, which is fine for a single-server project. A multi-server deployment would
need a shared store such as Redis.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone


class LoginLimiter:
    def __init__(self, window: timedelta = timedelta(minutes=15)):
        self.window = window
        self._failures: dict[str, list[datetime]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: datetime) -> list[datetime]:
        recent = [t for t in self._failures.get(key, []) if now - t < self.window]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def retry_after(self, key: str, max_attempts: int) -> int | None:
        """Seconds until the key may try again, or None if it is allowed now."""
        now = datetime.now(timezone.utc)
        with self._lock:
            recent = self._recent(key, now)
            if len(recent) < max_attempts:
                return None
            return max(1, int((recent[0] + self.window - now).total_seconds()) + 1)

    def record_failure(self, key: str) -> None:
        with self._lock:
            self._failures.setdefault(key, []).append(datetime.now(timezone.utc))

    def clear(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
