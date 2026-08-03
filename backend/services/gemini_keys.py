"""
Gemini API key pool with automatic rotation.

Free-tier Gemini keys each have their own per-minute request quota. Running
several keys and rotating on rate-limit (HTTP 429 / resource_exhausted) errors
multiplies that quota without any code changes at call sites: just use
`pick()` for the next key and `mark_rate_limited(key)` when a request fails.

All state is thread-safe because AI calls run in worker threads via
`asyncio.to_thread`.
"""

import os
import threading
import time

from config import GEMINI_API_KEY, GEMINI_API_KEYS

# Seconds a key rests after hitting its rate limit before it can be tried again.
RATE_LIMIT_COOLDOWN_SECONDS = float(os.getenv("GEMINI_KEY_COOLDOWN_SECONDS", "60"))


def _parse_keys() -> list[str]:
    """Build the ordered key list from GEMINI_API_KEY then GEMINI_API_KEYS.

    Both variables tolerate a comma-separated list, so a user can paste several
    keys on a single line.
    """
    keys: list[str] = []
    for raw in GEMINI_API_KEY.split(",") + GEMINI_API_KEYS.split(","):
        key = raw.strip()
        if key and key not in keys:
            keys.append(key)
    return keys


class _KeyPool:
    def __init__(self, keys: list[str]):
        self._keys = keys
        self._lock = threading.Lock()
        self._cursor = 0
        self._cooldowns: dict[str, float] = {}

    @property
    def size(self) -> int:
        return len(self._keys)

    def pick(self) -> str | None:
        """Return the next key that is not cooling down, or None if all are."""
        if not self._keys:
            return None
        with self._lock:
            now = time.time()
            expired = [k for k, until in self._cooldowns.items() if until <= now]
            for key in expired:
                del self._cooldowns[key]

            for _ in range(len(self._keys)):
                key = self._keys[self._cursor % len(self._keys)]
                self._cursor += 1
                if key not in self._cooldowns:
                    return key
        return None

    def mark_rate_limited(self, key: str) -> None:
        """Put a key into cooldown after a rate-limit error."""
        if not key:
            return
        with self._lock:
            self._cooldowns[key] = time.time() + RATE_LIMIT_COOLDOWN_SECONDS


_pool = _KeyPool(_parse_keys())


def next_key() -> str | None:
    """Return the next available API key (None when none are configured)."""
    return _pool.pick()


def mark_rate_limited(key: str) -> None:
    """Record a rate-limit failure for a key so it is skipped for a while."""
    _pool.mark_rate_limited(key)


def is_rate_limited_error(error: Exception) -> bool:
    """Return whether a Gemini error is a rate-limit / quota error."""
    code = str(getattr(error, "code", "")).lower()
    message = str(error).lower()
    return "429" in code or "resource_exhausted" in message
