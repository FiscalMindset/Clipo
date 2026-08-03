"""
PostgreSQL persistence + analytics layer.

Reads DATABASE_URL from config. When the database is not configured, every
function degrades to a safe no-op so the app still runs locally / without
Postgres (the legacy JSON file stores keep working as a fallback).
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

try:
    import bcrypt
except Exception:  # pragma: no cover
    bcrypt = None

try:
    import psycopg2
    import psycopg2.extras
except Exception:  # pragma: no cover
    psycopg2 = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _enabled() -> bool:
    from config import DATABASE_URL
    return bool(DATABASE_URL) and psycopg2 is not None


def _connect():
    from config import DATABASE_URL
    return psycopg2.connect(DATABASE_URL, connect_timeout=10)


def _fetchone(sql: str, params: Iterable | None = None) -> dict | None:
    if not _enabled():
        return None
    try:
        with _connect() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params or ())
            return cur.fetchone()
    except Exception:
        return None


def _fetchall(sql: str, params: Iterable | None = None) -> list[dict]:
    if not _enabled():
        return []
    try:
        with _connect() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()
    except Exception:
        return []


def _execute(sql: str, params: Iterable | None = None) -> None:
    if not _enabled():
        return
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params or ())
            conn.commit()
    except Exception:
        pass


def _scalar(sql: str, params: Iterable | None = None):
    row = _fetchone(sql, params)
    return row["n"] if row and row["n"] is not None else 0


def batch_insert(batches: list[tuple[list[list], str]]) -> None:
    """Insert many rows grouped by statement template in one transaction."""
    if not _enabled() or not batches:
        return
    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                for rows, sql in batches:
                    if rows:
                        cur.executemany(sql, rows)
            conn.commit()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Telemetry writes (used by services/telemetry.py)
# ─────────────────────────────────────────────────────────────────────────────

def upsert_backend(meta: dict) -> None:
    """Register (or refresh) a backend instance heartbeat."""
    if not _enabled() or not meta:
        return
    _execute(
        "INSERT INTO backends (backend_id, name, instance_id, version, region, status, started_at, last_seen) "
        "VALUES (%s,%s,%s,%s,%s,'online',%s, now()) "
        "ON CONFLICT (backend_id) DO UPDATE SET "
        "  name = EXCLUDED.name, instance_id = EXCLUDED.instance_id, version = EXCLUDED.version, "
        "  region = EXCLUDED.region, status = 'online', started_at = EXCLUDED.started_at, last_seen = now()",
        (
            meta.get("backend_id"), meta.get("name", ""), meta.get("instance_id", ""),
            meta.get("version", ""), meta.get("region", ""), meta.get("started_at"),
        ),
    )


def record_auth_event(
    user_id: str | None,
    email: str | None,
    status: str,
    error: str | None = None,
    *,
    context: dict | None = None,
    is_new: bool | None = None,
) -> None:
    """Record a sign-in event (success or failure) with full client context."""
    if not _enabled():
        return
    ctx = context or {}
    _execute(
        SQL_AUTH_EVENT_INSERT,
        (
            user_id, email, "google", status, error, is_new,
            ctx.get("frontend_origin"), ctx.get("frontend"),
            ctx.get("backend_id"), ctx.get("backend_name"), ctx.get("instance_id"),
            ctx.get("ip"), ctx.get("country"), ctx.get("user_agent"),
            ctx.get("browser"), ctx.get("os"), ctx.get("device"),
            _now(),
        ),
    )


def record_admin_audit(username: str, action: str, *, ip: str = "", user_agent: str = "", detail: str = "") -> None:
    if not _enabled():
        return
    _execute(SQL_ADMIN_AUDIT_INSERT, (username, action, ip, user_agent, detail))


# ─────────────────────────────────────────────────────────────────────────────
# Schema / init
# ─────────────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS admin_users (
    id            SERIAL PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    last_login    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS users (
    id           TEXT PRIMARY KEY,
    email        TEXT,
    name         TEXT,
    display_name TEXT DEFAULT '',
    picture      TEXT DEFAULT '',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login   TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id       TEXT PRIMARY KEY,
    user_id      TEXT,
    source_type  TEXT,
    status       TEXT,
    video_title  TEXT DEFAULT '',
    error        TEXT,
    ai_usage     JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS events (
    id          BIGSERIAL PRIMARY KEY,
    user_id     TEXT,
    event_name  TEXT NOT NULL,
    properties  JSONB DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_events_name   ON events (event_name);
CREATE INDEX IF NOT EXISTS idx_events_created ON events (created_at);
CREATE INDEX IF NOT EXISTS idx_events_user   ON events (user_id);

CREATE TABLE IF NOT EXISTS app_logs (
    id         BIGSERIAL PRIMARY KEY,
    level      TEXT NOT NULL,
    message    TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Backend instances / deployments that report telemetry.
CREATE TABLE IF NOT EXISTS backends (
    backend_id  TEXT PRIMARY KEY,
    name        TEXT DEFAULT '',
    instance_id TEXT DEFAULT '',
    version     TEXT DEFAULT '',
    region      TEXT DEFAULT '',
    status      TEXT DEFAULT 'online',
    started_at  TIMESTAMPTZ,
    last_seen   TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata    JSONB DEFAULT '{}'::jsonb
);

-- Every sign-in attempt (which frontend, which backend, IP, UA, result).
CREATE TABLE IF NOT EXISTS auth_events (
    id              BIGSERIAL PRIMARY KEY,
    user_id         TEXT,
    email           TEXT,
    provider        TEXT DEFAULT 'google',
    status          TEXT NOT NULL,
    error           TEXT,
    is_new          BOOLEAN,
    frontend_origin TEXT,
    frontend        TEXT,
    backend_id      TEXT,
    backend_name    TEXT,
    instance_id     TEXT,
    ip              TEXT,
    country         TEXT,
    user_agent      TEXT,
    browser         TEXT,
    os              TEXT,
    device          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_auth_events_created  ON auth_events (created_at);
CREATE INDEX IF NOT EXISTS idx_auth_events_email    ON auth_events (email);
CREATE INDEX IF NOT EXISTS idx_auth_events_frontend ON auth_events (frontend);
CREATE INDEX IF NOT EXISTS idx_auth_events_backend  ON auth_events (backend_id);
CREATE INDEX IF NOT EXISTS idx_auth_events_status   ON auth_events (status);

-- Per-request HTTP telemetry written by the request middleware.
CREATE TABLE IF NOT EXISTS request_logs (
    id              BIGSERIAL PRIMARY KEY,
    backend_id      TEXT,
    instance_id     TEXT,
    method          TEXT,
    path            TEXT,
    status          INT,
    duration_ms     INT,
    ip              TEXT,
    user_id         TEXT,
    frontend_origin TEXT,
    frontend        TEXT,
    browser         TEXT,
    os              TEXT,
    device          TEXT,
    user_agent      TEXT,
    referer         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_request_logs_created ON request_logs (created_at);
CREATE INDEX IF NOT EXISTS idx_request_logs_backend  ON request_logs (backend_id);
CREATE INDEX IF NOT EXISTS idx_request_logs_status   ON request_logs (status);
CREATE INDEX IF NOT EXISTS idx_request_logs_path     ON request_logs (path);

-- Structured server logs captured from the Python logging system.
CREATE TABLE IF NOT EXISTS server_logs (
    id          BIGSERIAL PRIMARY KEY,
    backend_id  TEXT,
    instance_id TEXT,
    level       TEXT NOT NULL,
    message     TEXT NOT NULL,
    logger      TEXT DEFAULT '',
    filename    TEXT DEFAULT '',
    lineno      INT,
    exc_info    TEXT DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_server_logs_created ON server_logs (created_at);
CREATE INDEX IF NOT EXISTS idx_server_logs_backend  ON server_logs (backend_id);
CREATE INDEX IF NOT EXISTS idx_server_logs_level    ON server_logs (level);

-- Admin panel audit trail (who did what in the admin panel).
CREATE TABLE IF NOT EXISTS admin_audit_logs (
    id             BIGSERIAL PRIMARY KEY,
    admin_username TEXT NOT NULL,
    action         TEXT NOT NULL,
    ip             TEXT DEFAULT '',
    user_agent     TEXT DEFAULT '',
    detail         TEXT DEFAULT '',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_admin_audit_created ON admin_audit_logs (created_at);
"""

# Statement templates used by the telemetry writer (batched inserts).
SQL_REQUEST_LOG_INSERT = (
    "INSERT INTO request_logs "
    "(backend_id, instance_id, method, path, status, duration_ms, ip, user_id, "
    " frontend_origin, frontend, browser, os, device, user_agent, referer, created_at) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)

SQL_SERVER_LOG_INSERT = (
    "INSERT INTO server_logs "
    "(backend_id, instance_id, level, message, logger, filename, lineno, exc_info, created_at) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)

SQL_AUTH_EVENT_INSERT = (
    "INSERT INTO auth_events "
    "(user_id, email, provider, status, error, is_new, frontend_origin, frontend, "
    " backend_id, backend_name, instance_id, ip, country, user_agent, browser, os, device, created_at) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)

SQL_ADMIN_AUDIT_INSERT = (
    "INSERT INTO admin_audit_logs (admin_username, action, ip, user_agent, detail) "
    "VALUES (%s,%s,%s,%s,%s)"
)


def init_db() -> None:
    """Create tables and seed admin users. Safe to call on every startup."""
    if not _enabled():
        print("DB: not configured — running with JSON-file storage only.")
        return
    _execute(SCHEMA)
    seed_admins()
    print("DB: connected and schema ready")


# ─────────────────────────────────────────────────────────────────────────────
# Admins
# ─────────────────────────────────────────────────────────────────────────────

def seed_admins() -> None:
    from config import ADMIN_PASSWORD, ADMIN_USERNAMES
    if bcrypt is None:
        return
    for username in ADMIN_USERNAMES:
        row = _fetchone("SELECT 1 AS ok FROM admin_users WHERE username = %s", (username,))
        if row:
            continue
        hashed = bcrypt.hashpw(ADMIN_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode()
        _execute("INSERT INTO admin_users (username, password_hash) VALUES (%s, %s)", (username, hashed))


def verify_admin(username: str, password: str) -> bool:
    if bcrypt is None:
        return False
    row = _fetchone("SELECT password_hash FROM admin_users WHERE username = %s", (username,))
    if not row:
        return False
    try:
        ok = bcrypt.checkpw(password.encode("utf-8"), row["password_hash"].encode("utf-8"))
    except ValueError:
        return False
    if ok:
        _execute("UPDATE admin_users SET last_login = %s WHERE username = %s", (_now(), username))
    return ok


# ─────────────────────────────────────────────────────────────────────────────
# Users
# ─────────────────────────────────────────────────────────────────────────────

def upsert_user(user: dict) -> bool:
    """Insert a user if new, else update last_login. Returns True when new."""
    if not _enabled():
        return False
    existing = _fetchone("SELECT 1 AS ok FROM users WHERE id = %s", (user.get("id"),))
    if existing:
        _execute(
            "UPDATE users SET email = %s, name = %s, display_name = %s, picture = %s, last_login = %s WHERE id = %s",
            (user.get("email"), user.get("name"), user.get("display_name", ""), user.get("picture", ""), _now(), user.get("id")),
        )
        return False
    _execute(
        "INSERT INTO users (id, email, name, display_name, picture, created_at, last_login) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (user.get("id"), user.get("email"), user.get("name"), user.get("display_name", ""),
         user.get("picture", ""), _now(), _now()),
    )
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Events (user behavior + usage)
# ─────────────────────────────────────────────────────────────────────────────

def record_event(user_id: str | None, event_name: str, properties: dict | None = None) -> None:
    if not _enabled():
        return
    _execute(
        "INSERT INTO events (user_id, event_name, properties) VALUES (%s, %s, %s)",
        (user_id, event_name, json.dumps(properties or {}, default=str)),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Jobs
# ─────────────────────────────────────────────────────────────────────────────

def sync_job(job: dict) -> None:
    if not _enabled() or not job:
        return
    _execute(
        "INSERT INTO jobs (job_id, user_id, source_type, status, video_title, error, ai_usage, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (job_id) DO UPDATE SET "
        "  status = EXCLUDED.status, video_title = EXCLUDED.video_title, "
        "  error = EXCLUDED.error, ai_usage = EXCLUDED.ai_usage, updated_at = EXCLUDED.updated_at",
        (
            job.get("job_id"), job.get("user_id"), job.get("source_type"), job.get("status"),
            job.get("video_title", ""), job.get("error"), json.dumps(job.get("ai_usage")) if job.get("ai_usage") else None,
            job.get("created_at", _now()), _now(),
        ),
    )


def sync_all_jobs(jobs: dict[str, dict]) -> None:
    for job in jobs.values():
        sync_job(job)


# ─────────────────────────────────────────────────────────────────────────────
# App logs
# ─────────────────────────────────────────────────────────────────────────────

def log_app(level: str, message: str) -> None:
    _execute("INSERT INTO app_logs (level, message) VALUES (%s, %s)", (level, message))


# ─────────────────────────────────────────────────────────────────────────────
# Admin analytics queries
# ─────────────────────────────────────────────────────────────────────────────

def get_stats() -> dict:
    """Aggregate overview numbers for the admin panel."""
    if not _enabled():
        return {}

    def scalar(sql, params=None):
        row = _fetchone(sql, params)
        return int(row["n"]) if row and row["n"] is not None else 0

    total_users = scalar("SELECT count(*) AS n FROM users")
    signups_7d = scalar("SELECT count(*) AS n FROM users WHERE created_at >= now() - interval '7 days'")
    total_jobs = scalar("SELECT count(*) AS n FROM jobs")
    jobs_7d = scalar("SELECT count(*) AS n FROM jobs WHERE created_at >= now() - interval '7 days'")
    jobs_completed = scalar("SELECT count(*) AS n FROM jobs WHERE status = 'completed'")
    jobs_failed = scalar("SELECT count(*) AS n FROM jobs WHERE status = 'failed'")
    events_24h = scalar("SELECT count(*) AS n FROM events WHERE created_at >= now() - interval '24 hours'")
    errors_24h = scalar("SELECT count(*) AS n FROM app_logs WHERE level = 'error' AND created_at >= now() - interval '24 hours'")

    signups_series = _fetchall(
        "SELECT to_char(date_trunc('day', created_at), 'YYYY-MM-DD') AS day, count(*) AS n "
        "FROM users WHERE created_at >= now() - interval '14 days' GROUP BY 1 ORDER BY 1"
    )
    jobs_series = _fetchall(
        "SELECT to_char(date_trunc('day', created_at), 'YYYY-MM-DD') AS day, count(*) AS n "
        "FROM jobs WHERE created_at >= now() - interval '14 days' GROUP BY 1 ORDER BY 1"
    )
    events_by_name = _fetchall(
        "SELECT event_name, count(*) AS n FROM events "
        "WHERE created_at >= now() - interval '14 days' GROUP BY event_name ORDER BY n DESC LIMIT 20"
    )

    return {
        "total_users": total_users,
        "signups_7d": signups_7d,
        "total_jobs": total_jobs,
        "jobs_7d": jobs_7d,
        "jobs_completed": jobs_completed,
        "jobs_failed": jobs_failed,
        "events_24h": events_24h,
        "errors_24h": errors_24h,
        "signups_series": signups_series,
        "jobs_series": jobs_series,
        "events_by_name": events_by_name,
    }


def list_users(limit: int = 25) -> list[dict]:
    return _fetchall(
        "SELECT id, email, name, display_name, created_at, last_login "
        "FROM users ORDER BY created_at DESC LIMIT %s", (limit,)
    )


def list_jobs(limit: int = 25) -> list[dict]:
    return _fetchall(
        "SELECT j.job_id, j.user_id, j.source_type, j.status, j.video_title, j.error, "
        "j.ai_usage, j.created_at, j.updated_at, "
        "u.email AS user_email, COALESCE(u.name, u.display_name, '') AS user_name, "
        "COALESCE(u.picture, '') AS user_picture "
        "FROM jobs j LEFT JOIN users u ON u.id = j.user_id "
        "ORDER BY j.created_at DESC LIMIT %s", (limit,)
    )


def list_events(limit: int = 40) -> list[dict]:
    return _fetchall(
        "SELECT id, user_id, event_name, properties, created_at "
        "FROM events ORDER BY created_at DESC LIMIT %s", (limit,)
    )


def list_logs(limit: int = 40) -> list[dict]:
    return _fetchall(
        "SELECT id, level, message, created_at FROM app_logs ORDER BY created_at DESC LIMIT %s", (limit,)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Pagination / filtering helpers
# ─────────────────────────────────────────────────────────────────────────────

def _page_params(page: int, per: int) -> tuple[int, int]:
    page = max(1, int(page or 1))
    per = max(1, min(200, int(per or 25)))
    return page, per


def _interval_cond(days: int | None) -> tuple[str, list]:
    if days and int(days) > 0:
        return "created_at >= now() - interval '%s days'" % int(days), []
    return "", []


def _paginate(sql_base: str, where: str, params: list, order: str, page: int, per: int, select_cols: str = "*") -> dict:
    page, per = _page_params(page, per)
    total = _scalar(f"SELECT count(*) AS n FROM {sql_base} {where}", params)
    rows = _fetchall(
        f"SELECT {select_cols} FROM {sql_base} {where} {order} LIMIT %s OFFSET %s",
        params + [per, (page - 1) * per],
    )
    pages = math.ceil(total / per) if total else 0
    return {"items": rows, "total": total, "page": page, "per": per, "pages": pages}


# ─────────────────────────────────────────────────────────────────────────────
# Analytics: summary
# ─────────────────────────────────────────────────────────────────────────────

def get_summary(days: int = 14) -> dict:
    """Rich dashboard KPIs + chart series for the admin panel."""
    if not _enabled():
        return {}

    stats = get_stats()
    days = max(7, min(90, int(days or 14)))

    signups_series = _fetchall(
        "SELECT to_char(date_trunc('day', created_at), 'YYYY-MM-DD') AS day, count(*) AS n "
        f"FROM users WHERE created_at >= now() - interval '{days} days' GROUP BY 1 ORDER BY 1"
    )
    logins_series = _fetchall(
        "SELECT to_char(date_trunc('day', created_at), 'YYYY-MM-DD') AS day, count(*) AS n "
        f"FROM auth_events WHERE status = 'success' AND created_at >= now() - interval '{days} days' GROUP BY 1 ORDER BY 1"
    )
    requests_series = _fetchall(
        "SELECT to_char(date_trunc('day', created_at), 'YYYY-MM-DD') AS day, count(*) AS n "
        f"FROM request_logs WHERE created_at >= now() - interval '{days} days' GROUP BY 1 ORDER BY 1"
    )

    total_logins = _scalar("SELECT count(*) AS n FROM auth_events WHERE status = 'success'")
    failed_logins = _scalar("SELECT count(*) AS n FROM auth_events WHERE status = 'failed'")
    logins_24h = _scalar("SELECT count(*) AS n FROM auth_events WHERE status = 'success' AND created_at >= now() - interval '24 hours'")
    requests_24h = _scalar("SELECT count(*) AS n FROM request_logs WHERE created_at >= now() - interval '24 hours'")
    requests_errors_24h = _scalar(
        "SELECT count(*) AS n FROM request_logs WHERE status >= 400 AND created_at >= now() - interval '24 hours'"
    )
    latency = _fetchone(
        "SELECT round(avg(duration_ms)) AS avg_ms, "
        "percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_ms "
        "FROM request_logs WHERE created_at >= now() - interval '7 days'"
    )
    active_users_7d = _scalar(
        "SELECT count(DISTINCT user_id) AS n FROM events WHERE created_at >= now() - interval '7 days'"
    )
    backends_online = _scalar("SELECT count(*) AS n FROM backends WHERE status = 'online'")
    online_counts = get_online_counts()

    top_endpoints = _fetchall(
        "SELECT method, path, count(*) AS n, round(avg(duration_ms)) AS avg_ms, max(duration_ms) AS max_ms, "
        "count(*) FILTER (WHERE status >= 400) AS errors "
        f"FROM request_logs WHERE path NOT LIKE '/admin%' AND created_at >= now() - interval '{days} days' "
        "GROUP BY method, path ORDER BY n DESC LIMIT 12"
    )

    return {
        **stats,
        "days": days,
        "total_logins": total_logins,
        "failed_logins": failed_logins,
        "logins_24h": logins_24h,
        "login_success_rate": round(total_logins * 100.0 / max(1, total_logins + failed_logins), 1),
        "requests_total": _scalar("SELECT count(*) AS n FROM request_logs"),
        "requests_24h": requests_24h,
        "request_error_rate_24h": round(requests_errors_24h * 100.0 / max(1, requests_24h), 1),
        "avg_latency_ms": int(latency["avg_ms"]) if latency and latency["avg_ms"] else 0,
        "p95_latency_ms": int(latency["p95_ms"]) if latency and latency["p95_ms"] else 0,
        "active_users_7d": active_users_7d,
        "backends_online": backends_online,
        "users_online_now": online_counts["now"],
        "users_active_1h": online_counts["last_1h"],
        "users_active_24h": online_counts["last_24h"],
        "top_users": get_top_users(days, 10),
        "job_source_mix": get_jobs_breakdown("source_type", days),
        "signups_series": _fill_daily(signups_series, days),
        "logins_series": _fill_daily(logins_series, days),
        "requests_series": _fill_daily(requests_series, days),
        "top_endpoints": top_endpoints,
    }


def _fill_daily(rows: list[dict], days: int) -> list[dict]:
    """Fill missing days with zero so chart series are continuous."""
    by_day = {r["day"]: r for r in rows}
    out = []
    start = _now() - timedelta(days=days - 1)
    for i in range(days):
        key = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        row = by_day.get(key)
        out.append({"day": key, "n": int(row["n"]) if row else 0})
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Analytics: timeseries / breakdown / latency / retention / top
# ─────────────────────────────────────────────────────────────────────────────

_TIMESERIES_SOURCES = {
    "signups": ("users", "users", "created_at"),
    "logins": ("auth_events", "auth_events", "created_at"),
    "login_failures": ("auth_events", "auth_events", "created_at"),
    "requests": ("request_logs", "request_logs", "created_at"),
    "events": ("events", "events", "created_at"),
    "jobs": ("jobs", "jobs", "created_at"),
}


def get_timeseries(metric: str, days: int = 14) -> list[dict]:
    if metric not in _TIMESERIES_SOURCES:
        return []
    alias, table, col = _TIMESERIES_SOURCES[metric]
    extra = " AND status = 'success'" if metric == "logins" else (" AND status = 'failed'" if metric == "login_failures" else "")
    days = max(1, min(180, int(days or 14)))
    rows = _fetchall(
        f"SELECT to_char(date_trunc('day', {col}), 'YYYY-MM-DD') AS day, count(*) AS n "
        f"FROM {table} WHERE {col} >= now() - interval '{days} days'{extra} GROUP BY 1 ORDER BY 1"
    )
    return _fill_daily(rows, days)


_AUTH_BREAKDOWN_DIMS = {"frontend", "backend", "device", "browser", "os", "status"}
_REQUEST_BREAKDOWN_DIMS = {"frontend", "backend", "device", "browser", "os", "method", "status"}


def get_breakdown(dimension: str, days: int = 14, kind: str = "auth") -> list[dict]:
    """Group a dimension into a ranked count list."""
    days = max(1, min(180, int(days or 14)))
    if kind == "requests":
        dim = dimension if dimension in _REQUEST_BREAKDOWN_DIMS else "path"
        col = "path" if dim == "path" else dim
        if col == "backend":
            col = "backend_id"
        return _fetchall(
            f"SELECT {col} AS label, count(*) AS n, "
            "count(*) FILTER (WHERE status >= 400) AS errors, round(avg(duration_ms)) AS avg_ms "
            f"FROM request_logs WHERE created_at >= now() - interval '{days} days' "
            f"GROUP BY {col} ORDER BY n DESC LIMIT 20"
        )
    dim = dimension if dimension in _AUTH_BREAKDOWN_DIMS else "frontend"
    col = "backend_id" if dim == "backend" else dim
    return _fetchall(
        f"SELECT {col} AS label, count(*) AS n, "
        "count(*) FILTER (WHERE status = 'success') AS success, "
        "count(*) FILTER (WHERE status = 'failed') AS failed "
        f"FROM auth_events WHERE created_at >= now() - interval '{days} days' "
        f"GROUP BY {col} ORDER BY n DESC LIMIT 20"
    )


_JOBS_BREAKDOWN_DIMS = {"source_type", "status", "user", "provider"}


def get_jobs_breakdown(dimension: str, days: int = 14) -> list[dict]:
    """Group jobs by a dimension (source_type / status / user / AI provider)."""
    if not _enabled():
        return []
    days = max(1, min(180, int(days or 14)))
    if dimension == "user":
        return _fetchall(
            "SELECT COALESCE(u.email, j.user_id, 'unknown') AS label, count(*) AS n, "
            "count(*) FILTER (WHERE j.status = 'completed') AS completed, "
            "count(*) FILTER (WHERE j.status = 'failed') AS failed "
            f"FROM jobs j LEFT JOIN users u ON u.id = j.user_id "
            f"WHERE j.created_at >= now() - interval '{days} days' "
            "GROUP BY 1 ORDER BY n DESC LIMIT 20"
        )
    dim = dimension if dimension in _JOBS_BREAKDOWN_DIMS else "source_type"
    col = "COALESCE(j.ai_usage->>'provider', 'none')" if dim == "provider" else dim
    return _fetchall(
        f"SELECT {col} AS label, count(*) AS n, "
        "count(*) FILTER (WHERE j.status = 'completed') AS completed, "
        "count(*) FILTER (WHERE j.status = 'failed') AS failed "
        f"FROM jobs j WHERE j.created_at >= now() - interval '{days} days' "
        "GROUP BY 1 ORDER BY n DESC LIMIT 20"
    )


def get_online_counts() -> dict:
    """Distinct active users over the last 5 minutes / 1 hour / 24 hours."""
    if not _enabled():
        return {"now": 0, "last_1h": 0, "last_24h": 0}

    def cnt(minutes: int) -> int:
        return _scalar(
            "SELECT count(DISTINCT user_id) AS n FROM request_logs "
            "WHERE user_id IS NOT NULL AND created_at >= now() - interval '%s minutes'" % int(minutes)
        )

    return {"now": cnt(5), "last_1h": cnt(60), "last_24h": cnt(1440)}


def get_online_users(minutes: int = 15) -> list[dict]:
    """Users with activity in the last N minutes + what they were doing last."""
    if not _enabled():
        return []
    minutes = max(1, min(1440, int(minutes or 15)))
    return _fetchall(
        "SELECT r.user_id AS id, "
        "COALESCE(u.email, '') AS email, COALESCE(u.name, '') AS name, "
        "COALESCE(u.display_name, '') AS display_name, COALESCE(u.picture, '') AS picture, "
        "u.last_login AS last_login, "
        "count(*) AS requests, count(*) FILTER (WHERE r.status >= 400) AS errors, "
        "max(r.created_at) AS last_seen, "
        "(SELECT r2.method FROM request_logs r2 "
        " WHERE r2.user_id = r.user_id AND r2.created_at >= now() - interval '%s minutes' "
        " ORDER BY r2.created_at DESC LIMIT 1) AS last_method, "
        "(SELECT r2.path FROM request_logs r2 "
        " WHERE r2.user_id = r.user_id AND r2.created_at >= now() - interval '%s minutes' "
        " ORDER BY r2.created_at DESC LIMIT 1) AS last_path, "
        "(SELECT r2.frontend FROM request_logs r2 "
        " WHERE r2.user_id = r.user_id AND r2.created_at >= now() - interval '%s minutes' "
        " ORDER BY r2.created_at DESC LIMIT 1) AS last_frontend, "
        "(SELECT r2.ip FROM request_logs r2 "
        " WHERE r2.user_id = r.user_id AND r2.created_at >= now() - interval '%s minutes' "
        " ORDER BY r2.created_at DESC LIMIT 1) AS last_ip, "
        "(SELECT r2.device FROM request_logs r2 "
        " WHERE r2.user_id = r.user_id AND r2.created_at >= now() - interval '%s minutes' "
        " ORDER BY r2.created_at DESC LIMIT 1) AS last_device, "
        "(SELECT e.event_name FROM events e "
        " WHERE e.user_id = r.user_id AND e.created_at >= now() - interval '%s minutes' "
        " ORDER BY e.created_at DESC LIMIT 1) AS last_event "
        "FROM request_logs r LEFT JOIN users u ON u.id = r.user_id "
        "WHERE r.user_id IS NOT NULL AND r.created_at >= now() - interval '%s minutes' "
        "GROUP BY r.user_id, u.email, u.name, u.display_name, u.picture, u.last_login "
        "ORDER BY last_seen DESC"
        % (minutes, minutes, minutes, minutes, minutes, minutes, minutes)
    )


def get_top_users(days: int = 14, limit: int = 10) -> list[dict]:
    """Most active users by request volume in the last N days."""
    if not _enabled():
        return []
    days = max(1, min(180, int(days or 14)))
    return _fetchall(
        "SELECT r.user_id AS id, COALESCE(u.email, '') AS email, "
        "COALESCE(u.name, '') AS name, COALESCE(u.picture, '') AS picture, "
        "count(*) AS requests, count(*) FILTER (WHERE r.status >= 400) AS errors, "
        "max(r.created_at) AS last_seen, "
        "(SELECT count(*) FROM jobs j WHERE j.user_id = r.user_id) AS total_jobs "
        f"FROM request_logs r LEFT JOIN users u ON u.id = r.user_id "
        f"WHERE r.user_id IS NOT NULL AND r.created_at >= now() - interval '{days} days' "
        "GROUP BY r.user_id, u.email, u.name, u.picture "
        "ORDER BY requests DESC LIMIT %s",
        (int(limit),),
    )


def get_latency_series(days: int = 14) -> list[dict]:
    days = max(1, min(180, int(days or 14)))
    rows = _fetchall(
        "SELECT to_char(date_trunc('day', created_at), 'YYYY-MM-DD') AS day, "
        "round(avg(duration_ms)) AS avg_ms, "
        "percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_ms, count(*) AS n "
        f"FROM request_logs WHERE created_at >= now() - interval '{days} days' GROUP BY 1 ORDER BY 1"
    )
    return _fill_daily_latency(rows, days)


def _fill_daily_latency(rows: list[dict], days: int) -> list[dict]:
    by_day = {r["day"]: r for r in rows}
    out = []
    start = _now() - timedelta(days=days - 1)
    for i in range(days):
        key = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        row = by_day.get(key)
        out.append({
            "day": key,
            "avg_ms": int(row["avg_ms"]) if row and row["avg_ms"] else 0,
            "p95_ms": int(row["p95_ms"]) if row and row["p95_ms"] else 0,
            "n": int(row["n"]) if row else 0,
        })
    return out


def get_retention(weeks: int = 8) -> list[dict]:
    """Simple weekly cohort retention based on first behavior event activity."""
    if not _enabled():
        return []
    cohorts = _fetchall(
        "SELECT to_char(date_trunc('week', created_at), 'YYYY-MM-DD') AS week, id "
        "FROM users WHERE created_at >= now() - interval '%s weeks'" % max(2, weeks)
    )
    activity = _fetchall(
        "SELECT user_id, to_char(date_trunc('week', created_at), 'YYYY-MM-DD') AS week "
        "FROM events WHERE created_at >= now() - interval '%s weeks'" % (weeks + 2)
    )
    active_by_user: dict[str, set] = {}
    for row in activity:
        active_by_user.setdefault(row["user_id"], set()).add(row["week"])

    cohort_users: dict[str, list] = {}
    for row in cohorts:
        cohort_users.setdefault(row["week"], []).append(row["id"])

    weeks_sorted = sorted(cohort_users.keys())[-weeks:]
    result = []
    for i, week in enumerate(weeks_sorted):
        members = cohort_users[week]
        size = len(members)
        retention = []
        for offset in range(0, 4):
            target = week
            if offset > 0:
                from datetime import datetime as _dt
                try:
                    base = _dt.strptime(week, "%Y-%m-%d").date()
                except ValueError:
                    break
                target = (base + timedelta(weeks=offset)).strftime("%Y-%m-%d")
            count = sum(1 for uid in members if target in active_by_user.get(uid, set()))
            retention.append(round(count * 100.0 / max(1, size), 1))
        result.append({"week": week, "size": size, "retention": retention})
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Analytics: listing endpoints
# ─────────────────────────────────────────────────────────────────────────────

def list_auth_events(filters: dict | None = None, page: int = 1, per: int = 25) -> dict:
    filters = filters or {}
    conds: list[str] = []
    params: list = []
    if filters.get("q"):
        like = f"%{filters['q']}%"
        conds.append("(email ILIKE %s OR ip ILIKE %s OR user_id ILIKE %s OR frontend ILIKE %s)")
        params += [like, like, like, like]
    for key in ("frontend", "backend_id", "backend_name", "status", "device", "browser", "os"):
        if filters.get(key):
            conds.append(f"{key} = %s")
            params.append(filters[key])
    if filters.get("backend"):
        conds.append("backend_id = %s")
        params.append(filters["backend"])
    if filters.get("email"):
        conds.append("email = %s")
        params.append(filters["email"])
    days = filters.get("days")
    if days:
        conds.append("created_at >= now() - interval '%s days'" % int(days))
    where = _where(conds)
    return _paginate("auth_events", where, params, "ORDER BY created_at DESC", page, per)


def list_requests(filters: dict | None = None, page: int = 1, per: int = 25) -> dict:
    filters = filters or {}
    conds: list[str] = []
    params: list = []
    if filters.get("q"):
        like = f"%{filters['q']}%"
        conds.append("(path ILIKE %s OR ip ILIKE %s OR user_id ILIKE %s)")
        params += [like, like, like]
    for key in ("method", "status", "backend_id", "frontend", "device", "os", "browser"):
        if filters.get(key):
            conds.append(f"{key} = %s")
            params.append(filters[key])
    if filters.get("backend"):
        conds.append("backend_id = %s")
        params.append(filters["backend"])
    if filters.get("path"):
        conds.append("path ILIKE %s")
        params.append(f"%{filters['path']}%")
    if filters.get("min_status"):
        conds.append("status >= %s")
        params.append(int(filters["min_status"]))
    days = filters.get("days")
    if days:
        conds.append("created_at >= now() - interval '%s days'" % int(days))
    where = _where(conds)
    return _paginate("request_logs", where, params, "ORDER BY created_at DESC", page, per)


def list_server_logs(filters: dict | None = None, page: int = 1, per: int = 50) -> dict:
    filters = filters or {}
    conds: list[str] = []
    params: list = []
    if filters.get("q"):
        conds.append("message ILIKE %s")
        params.append(f"%{filters['q']}%")
    for key in ("level", "backend_id", "logger"):
        if filters.get(key):
            conds.append(f"{key} = %s")
            params.append(filters[key])
    if filters.get("backend"):
        conds.append("backend_id = %s")
        params.append(filters["backend"])
    days = filters.get("days")
    if days:
        conds.append("created_at >= now() - interval '%s days'" % int(days))
    where = _where(conds)
    return _paginate("server_logs", where, params, "ORDER BY created_at DESC", page, per)


def list_backends() -> list[dict]:
    return _fetchall(
        "SELECT b.*, "
        "(SELECT count(*) FROM request_logs r WHERE r.backend_id = b.backend_id AND r.created_at >= now() - interval '1 hour') AS req_1h, "
        "(SELECT count(*) FROM request_logs r WHERE r.backend_id = b.backend_id AND r.status >= 400 AND r.created_at >= now() - interval '1 hour') AS err_1h, "
        "(SELECT count(*) FROM request_logs r WHERE r.backend_id = b.backend_id) AS req_total "
        "FROM backends b ORDER BY b.last_seen DESC"
    )


def list_users_paginated(filters: dict | None = None, page: int = 1, per: int = 25) -> dict:
    filters = filters or {}
    conds: list[str] = []
    params: list = []
    if filters.get("q"):
        like = f"%{filters['q']}%"
        conds.append("(email ILIKE %s OR name ILIKE %s OR id ILIKE %s)")
        params += [like, like, like]
    if filters.get("days"):
        conds.append("created_at >= now() - interval '%s days'" % int(filters["days"]))
    where = _where(conds)
    return _paginate("users", where, params, "ORDER BY created_at DESC", page, per)


def list_jobs_paginated(filters: dict | None = None, page: int = 1, per: int = 25) -> dict:
    filters = filters or {}
    conds: list[str] = []
    params: list = []
    if filters.get("q"):
        like = f"%{filters['q']}%"
        conds.append("(j.job_id ILIKE %s OR j.user_id ILIKE %s OR j.video_title ILIKE %s "
                     "OR u.email ILIKE %s OR u.name ILIKE %s)")
        params += [like, like, like, like, like]
    for key in ("status", "source_type", "user_id"):
        if filters.get(key):
            conds.append(f"j.{key} = %s")
            params.append(filters[key])
    if filters.get("provider"):
        conds.append("COALESCE(j.ai_usage->>'provider', '') = %s")
        params.append(filters["provider"])
    if filters.get("days"):
        conds.append("j.created_at >= now() - interval '%s days'" % int(filters["days"]))
    where = _where(conds)
    base = "jobs j LEFT JOIN users u ON u.id = j.user_id"
    cols = (
        "j.job_id, j.user_id, j.source_type, j.status, j.video_title, j.error, "
        "j.ai_usage, j.created_at, j.updated_at, "
        "u.email AS user_email, COALESCE(u.name, u.display_name, '') AS user_name, "
        "COALESCE(u.picture, '') AS user_picture"
    )
    return _paginate(base, where, params, "ORDER BY j.created_at DESC", page, per, select_cols=cols)


def list_events_paginated(filters: dict | None = None, page: int = 1, per: int = 50) -> dict:
    filters = filters or {}
    conds: list[str] = []
    params: list = []
    if filters.get("q"):
        like = f"%{filters['q']}%"
        conds.append("(event_name ILIKE %s OR user_id ILIKE %s)")
        params += [like, like]
    if filters.get("event_name"):
        conds.append("event_name = %s")
        params.append(filters["event_name"])
    if filters.get("user_id"):
        conds.append("user_id = %s")
        params.append(filters["user_id"])
    days = filters.get("days")
    if days:
        conds.append("created_at >= now() - interval '%s days'" % int(days))
    where = _where(conds)
    return _paginate("events", where, params, "ORDER BY created_at DESC", page, per)


# ─────────────────────────────────────────────────────────────────────────────
# Admin account management
# ─────────────────────────────────────────────────────────────────────────────

def list_admins() -> list[dict]:
    return _fetchall("SELECT id, username, last_login FROM admin_users ORDER BY username")


def create_admin(username: str, password: str) -> bool:
    if bcrypt is None or not username or not password:
        return False
    exists = _fetchone("SELECT 1 AS ok FROM admin_users WHERE username = %s", (username,))
    if exists:
        return False
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode()
    _execute("INSERT INTO admin_users (username, password_hash) VALUES (%s, %s)", (username, hashed))
    return True


def delete_admin(username: str) -> bool:
    if not username:
        return False
    count = _scalar("SELECT count(*) AS n FROM admin_users")
    if count <= 1:
        return False
    _execute("DELETE FROM admin_users WHERE username = %s", (username,))
    return True


def set_admin_password(username: str, password: str) -> bool:
    if bcrypt is None or not password:
        return False
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode()
    _execute("UPDATE admin_users SET password_hash = %s WHERE username = %s", (hashed, username))
    return True


def list_admin_audit(filters: dict | None = None, page: int = 1, per: int = 50) -> dict:
    filters = filters or {}
    conds: list[str] = []
    params: list = []
    if filters.get("q"):
        like = f"%{filters['q']}%"
        conds.append("(admin_username ILIKE %s OR action ILIKE %s OR detail ILIKE %s)")
        params += [like, like, like]
    if filters.get("admin"):
        conds.append("admin_username = %s")
        params.append(filters["admin"])
    days = filters.get("days")
    if days:
        conds.append("created_at >= now() - interval '%s days'" % int(days))
    where = _where(conds)
    return _paginate("admin_audit_logs", where, params, "ORDER BY created_at DESC", page, per)


# ─────────────────────────────────────────────────────────────────────────────
# Exports (CSV-friendly row lists)
# ─────────────────────────────────────────────────────────────────────────────

def export_users(days: int | None = None) -> list[dict]:
    where = ""
    if days:
        where = f" WHERE created_at >= now() - interval '{int(days)} days'"
    return _fetchall(f"SELECT id, email, name, display_name, created_at, last_login FROM users{where} ORDER BY created_at DESC")


def export_auth_events(days: int | None = None) -> list[dict]:
    where = ""
    if days:
        where = f" WHERE created_at >= now() - interval '{int(days)} days'"
    return _fetchall(
        f"SELECT id, created_at, user_id, email, provider, status, error, is_new, frontend, frontend_origin, "
        f"backend_id, backend_name, instance_id, ip, country, browser, os, device FROM auth_events{where} ORDER BY created_at DESC"
    )


def export_requests(days: int | None = None) -> list[dict]:
    where = ""
    if days:
        where = f" WHERE created_at >= now() - interval '{int(days)} days'"
    return _fetchall(
        f"SELECT id, created_at, backend_id, instance_id, method, path, status, duration_ms, ip, user_id, "
        f"frontend, frontend_origin, browser, os, device FROM request_logs{where} ORDER BY created_at DESC"
    )


def export_server_logs(days: int | None = None) -> list[dict]:
    where = ""
    if days:
        where = f" WHERE created_at >= now() - interval '{int(days)} days'"
    return _fetchall(
        f"SELECT id, created_at, backend_id, instance_id, level, logger, filename, lineno, message, exc_info "
        f"FROM server_logs{where} ORDER BY created_at DESC"
    )


def export_events(days: int | None = None) -> list[dict]:
    where = ""
    if days:
        where = f" WHERE created_at >= now() - interval '{int(days)} days'"
    return _fetchall(
        f"SELECT id, created_at, user_id, event_name, properties FROM events{where} ORDER BY created_at DESC"
    )


def export_jobs(days: int | None = None) -> list[dict]:
    where = ""
    if days:
        where = f" WHERE j.created_at >= now() - interval '{int(days)} days'"
    return _fetchall(
        f"SELECT j.job_id, j.user_id, j.source_type, j.status, j.video_title, j.error, "
        f"j.ai_usage, j.created_at, j.updated_at, "
        f"u.email AS user_email, COALESCE(u.name, u.display_name, '') AS user_name "
        f"FROM jobs j LEFT JOIN users u ON u.id = j.user_id{where} ORDER BY j.created_at DESC"
    )


def _where(conds: list[str]) -> str:
    return (" WHERE " + " AND ".join(conds)) if conds else ""
