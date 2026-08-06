"""
Gemini API key access.

The backend uses a single Gemini API key (config.GEMINI_API_KEY). Free-tier keys
carry a small daily request quota; when it runs out, the AI service sees a 429
rate-limit error and retries with backoff until the quota resets.

A multi-key rotation pool is intentionally not used: Google detects and suspends
keys pooled to multiply the free-tier quota (HTTP 403 CONSUMER_SUSPENDED).
"""

from config import GEMINI_API_KEY


def next_key() -> str | None:
    """Return the configured Gemini API key, or None when not set."""
    key = GEMINI_API_KEY.strip() if GEMINI_API_KEY else ""
    return key or None


def mark_rate_limited(key: str) -> None:
    """No-op kept for compatibility; 429 handling is done by retry/backoff."""


def is_rate_limited_error(error: Exception) -> bool:
    """Return whether a Gemini error is a rate-limit / quota error."""
    code = str(getattr(error, "code", "")).lower()
    message = str(error).lower()
    return "429" in code or "resource_exhausted" in message
