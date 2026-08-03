"""
Telemetry infrastructure for Clipo backend.

Provides:
  * Backend identity (BACKEND_ID / INSTANCE_ID from config).
  * Client context extraction: IP, user-agent -> browser/OS/device, frontend
    origin -> friendly name.
  * A buffered async DB writer so telemetry never blocks the request path.
  * FastAPI middleware that logs every API request (method, path, status,
    duration, client) into `request_logs`.
  * A logging.Handler that mirrors structured log records into `server_logs`
    with backend/instance context.

Everything degrades safely to no-op when Postgres is not configured.
"""

from __future__ import annotations

import json
import logging
import queue
import re
import threading
import time
from datetime import datetime, timezone

from config import (
    BACKEND_ID,
    BACKEND_NAME,
    BACKEND_REGION,
    BACKEND_VERSION,
    INSTANCE_ID,
    JWT_SECRET,
    TELEMETRY_ENABLED,
    TELEMETRY_FLUSH_SECONDS,
    TELEMETRY_MAX_BUFFER,
    frontend_name,
)
from services import db

log = logging.getLogger("clipo.telemetry")

# ─────────────────────────────────────────────────────────────────────────────
# Backend identity
# ─────────────────────────────────────────────────────────────────────────────

BACKEND = {
    "backend_id": BACKEND_ID,
    "name": BACKEND_NAME,
    "instance_id": INSTANCE_ID,
    "version": BACKEND_VERSION,
    "region": BACKEND_REGION,
    "started_at": datetime.now(timezone.utc).isoformat(),
}

# ─────────────────────────────────────────────────────────────────────────────
# Buffered DB writer
# ─────────────────────────────────────────────────────────────────────────────

class _Buffer:
    """Thread-safe FIFO buffer consumed by a single writer thread."""

    def __init__(self) -> None:
        self._q: queue.Queue[tuple[list[list], str]] = queue.Queue()
        self._lock = threading.Lock()
        self._batch: list[tuple[list[list], str]] = []

    def add(self, rows: list[list], sql: str) -> None:
        self._q.put((rows, sql))

    def drain(self, max_items: int) -> list[tuple[list[list], str]]:
        out: list[tuple[list[list], str]] = []
        while len(out) < max_items:
            try:
                out.append(self._q.get_nowait())
            except queue.Empty:
                break
        return out


_BUFFER = _Buffer()


def _flush() -> None:
    """Flush buffered rows to Postgres in one batch (called on writer thread)."""
    if not db._enabled():
        return
    batches = _BUFFER.drain(TELEMETRY_MAX_BUFFER)
    if not batches:
        return
    try:
        db.batch_insert(batches)
    except Exception as exc:  # noqa: BLE001
        log.warning("telemetry flush failed: %s", exc)


def _writer_loop() -> None:
    while True:
        try:
            time.sleep(TELEMETRY_FLUSH_SECONDS)
            _flush()
        except Exception as exc:  # noqa: BLE001
            log.warning("telemetry writer error: %s", exc)


def _start_writer() -> None:
    if not db._enabled() or not TELEMETRY_ENABLED:
        return
    thread = threading.Thread(target=_writer_loop, name="clipo-telemetry-writer", daemon=True)
    thread.start()
    log.info("telemetry writer started (flush every %ss)", TELEMETRY_FLUSH_SECONDS)


# ─────────────────────────────────────────────────────────────────────────────
# Client context parsing
# ─────────────────────────────────────────────────────────────────────────────

def _parse_ua(user_agent: str) -> dict[str, str]:
    """Lightweight, dependency-free browser/OS/device parsing."""
    ua = (user_agent or "").strip()
    if not ua:
        return {"browser": "unknown", "os": "unknown", "device": "unknown"}

    device = "unknown"
    if re.search(r"iPad|Tablet|Kindle|Silk|PlayBook", ua):
        device = "tablet"
    elif re.search(r"iPhone|iPod|Android.*Mobile|Mobile|Opera Mini|Windows Phone", ua):
        device = "mobile"
    elif re.search(r"(Macintosh|Windows NT|Linux|X11|CrOS)", ua):
        device = "desktop"

    os_name = "unknown"
    for key, name in (
        ("Windows NT 10", "Windows 10"),
        ("Windows NT 6.3", "Windows 8.1"),
        ("Windows NT 6.1", "Windows 7"),
        ("Windows Phone", "Windows Phone"),
        ("Windows", "Windows"),
        ("Mac OS X", "macOS"),
        ("Macintosh", "macOS"),
        ("iPhone OS", "iOS"),
        ("iPad OS", "iOS"),
        ("iPhone", "iOS"),
        ("iPad", "iOS"),
        ("Android", "Android"),
        ("CrOS", "Chrome OS"),
        ("Linux", "Linux"),
        ("X11", "Linux"),
    ):
        if key in ua:
            os_name = name
            break

    browser = "unknown"
    if "Edg/" in ua or "Edge/" in ua:
        browser = "Edge"
    elif "OPR/" in ua or "Opera" in ua:
        browser = "Opera"
    elif "SamsungBrowser" in ua:
        browser = "Samsung Internet"
    elif re.search(r"Chrome/|CriOS|Chromium", ua):
        browser = "Chrome"
    elif re.search(r"Firefox/|FxiOS", ua):
        browser = "Firefox"
    elif re.search(r"Safari/|Version/", ua) and "AppleWebKit" in ua:
        browser = "Safari"
    elif "MSIE" in ua or "Trident/" in ua:
        browser = "Internet Explorer"

    return {"browser": browser, "os": os_name, "device": device}


def client_context(request) -> dict[str, str]:
    """Extract IP, user-agent and frontend origin for a request."""
    ip = request.headers.get("X-Forwarded-For", "")
    if not ip and getattr(request, "client", None):
        ip = request.client.host or ""
    # X-Forwarded-For may be a comma-separated chain; the client is the first hop.
    if ip and "," in ip:
        ip = ip.split(",")[0].strip()
    ua = request.headers.get("User-Agent", "")
    parsed = _parse_ua(ua)
    origin = request.headers.get("Origin", "") or request.headers.get("Referer", "").rstrip("/")
    return {
        "ip": ip or "unknown",
        "frontend_origin": origin,
        "frontend": frontend_name(origin),
        "user_agent": ua[:512],
        "browser": parsed["browser"],
        "os": parsed["os"],
        "device": parsed["device"],
        "referer": (request.headers.get("Referer", "") or "")[:512],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Request logging middleware
# ─────────────────────────────────────────────────────────────────────────────

_SKIP_PATHS = ("/static", "/admin/app", "/favicon.ico", "/docs", "/redoc", "/openapi.json")


async def request_middleware(request, call_next):
    """Starlette-style pure ASGI middleware that records request telemetry."""
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        _record_request(request, 500, int((time.perf_counter() - start) * 1000))
        raise
    duration_ms = int((time.perf_counter() - start) * 1000)
    if response is not None:
        _record_request(request, response.status_code, duration_ms)
    return response


def _record_request(request, status_code: int, duration_ms: int) -> None:
    if not db._enabled() or not TELEMETRY_ENABLED:
        return
    path = request.url.path
    if any(path.startswith(p) for p in _SKIP_PATHS):
        return
    ctx = client_context(request)

    # Cheap user id lookup when an Authorization header is present.
    user_id = None
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            from jose import jwt as _jwt
            payload = _jwt.decode(auth[7:].strip(), JWT_SECRET, algorithms=["HS256"])
            user_id = payload.get("sub")
        except Exception:  # noqa: BLE001
            user_id = None

    row = [
        BACKEND["backend_id"],
        BACKEND["instance_id"],
        request.method,
        path,
        status_code,
        duration_ms,
        ctx["ip"],
        user_id,
        ctx["frontend_origin"],
        ctx["frontend"],
        ctx["browser"],
        ctx["os"],
        ctx["device"],
        ctx["user_agent"],
        ctx["referer"],
        datetime.now(timezone.utc),
    ]
    _BUFFER.add([row], db.SQL_REQUEST_LOG_INSERT)


# ─────────────────────────────────────────────────────────────────────────────
# Structured logging handler
# ─────────────────────────────────────────────────────────────────────────────

class PostgresLogHandler(logging.Handler):
    """Batches logging records into the server_logs table."""

    def emit(self, record: logging.LogRecord) -> None:  # noqa: A003
        try:
            if not db._enabled() or not TELEMETRY_ENABLED:
                return
            exc_text = record.exc_text or ""
            if record.exc_info:
                exc_text = self.formatException(record.exc_info)
            extra = json.dumps(
                {
                    k: str(v)
                    for k, v in (getattr(record, "extra", {}) or {}).items()
                },
                default=str,
            )
            row = [
                BACKEND["backend_id"],
                BACKEND["instance_id"],
                record.levelname.lower(),
                record.getMessage()[:4000],
                record.name,
                record.filename,
                record.lineno,
                exc_text[:4000],
                datetime.now(timezone.utc),
            ]
            _BUFFER.add([row], db.SQL_SERVER_LOG_INSERT)
        except Exception:  # noqa: BLE001
            pass  # logging must never raise


def attach_logging_handler(logger: logging.Logger | None = None) -> None:
    """Attach the Postgres handler to a logger (defaults to root).

    uvicorn's loggers set ``propagate=False``, so they never reach root; attach
    the same handler to them directly so access/error/startup lines land in
    ``server_logs`` too.
    """
    if not db._enabled() or not TELEMETRY_ENABLED:
        return
    handler = PostgresLogHandler(level=logging.INFO)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    (logger or logging.getLogger()).addHandler(handler)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi"):
        try:
            logging.getLogger(name).addHandler(handler)
        except Exception:  # noqa: BLE001
            pass


def start() -> None:
    """Initialize telemetry: backend registration + writer thread."""
    if not db._enabled():
        return
    db.upsert_backend(BACKEND)
    _start_writer()


def flush() -> None:
    """Synchronously flush pending telemetry (used on shutdown)."""
    try:
        _flush()
    except Exception:  # noqa: BLE001
        pass
