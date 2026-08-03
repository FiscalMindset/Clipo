"""
PostgreSQL persistence + analytics layer.

Reads DATABASE_URL from config. When the database is not configured, every
function degrades to a safe no-op so the app still runs locally / without
Postgres (the legacy JSON file stores keep working as a fallback).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
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

CREATE TABLE IF NOT EXISTS app_logs (
    id         BIGSERIAL PRIMARY KEY,
    level      TEXT NOT NULL,
    message    TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


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
        "SELECT job_id, user_id, source_type, status, video_title, error, created_at, updated_at "
        "FROM jobs ORDER BY created_at DESC LIMIT %s", (limit,)
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
