"""
Clipo admin API + panel.

  * JSON API lives under /admin/api/* (JWT bearer protected) and powers the
    admin SPA. Includes analytics (summary, timeseries, breakdown, latency,
    retention), sign-in session tracing (which frontend + which backend + IP),
    request logs, structured server logs, backend health, user/job/event
    browsing, admin account management and CSV export.
  * The SPA itself is served as static files from /admin/app/ (see main.py);
    /admin redirects there.

Every mutating or notable read is written to the admin audit trail.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, Response
from jose import jwt, JWTError

from config import JWT_SECRET, JWT_ALGORITHM
from services import db
from services import telemetry

router = APIRouter(prefix="/admin")

ADMIN_EXPIRE_HOURS = 24


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _require_admin(request: Request) -> str:
    """Validate the admin bearer token; returns the admin username."""
    auth = request.headers.get("Authorization", "")
    # Fall back to ?token= so browser navigation (CSV export links) works.
    if not auth.lower().startswith("bearer ") and request.query_params.get("token"):
        auth = f"Bearer {request.query_params['token']}"
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = auth[7:].strip()
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not an admin")
    return payload.get("sub", "")


def _client_ip(request: Request) -> str:
    ip = request.headers.get("X-Forwarded-For", "")
    if ip and "," in ip:
        ip = ip.split(",")[0].strip()
    return ip or (getattr(request, "client", None).host if getattr(request, "client", None) else "")


def _audit(request: Request, admin: str, action: str, detail: str = "") -> None:
    try:
        db.record_admin_audit(
            admin, action,
            ip=_client_ip(request),
            user_agent=request.headers.get("User-Agent", ""),
            detail=detail,
        )
    except Exception:
        pass


def _filters(request: Request, keys: list[str]) -> dict:
    return {k: request.query_params.get(k) for k in keys if request.query_params.get(k) is not None}


def _int_qp(request: Request, key: str, default: int) -> int:
    try:
        return int(request.query_params.get(key, default))
    except (TypeError, ValueError):
        return default


# ─────────────────────────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/login")
async def admin_login(request: Request, body: dict):
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")
    ok = db.verify_admin(username, password)
    db.record_admin_audit(username, "login", ip=_client_ip(request),
                          user_agent=request.headers.get("User-Agent", ""),
                          detail="success" if ok else "failed")
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    payload = {
        "sub": username,
        "role": "admin",
        "exp": datetime.now(timezone.utc) + timedelta(hours=ADMIN_EXPIRE_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {"token": token, "username": username, "expires_in": ADMIN_EXPIRE_HOURS * 3600}


@router.get("/api/me")
async def admin_me(request: Request):
    admin = _require_admin(request)
    return {
        "username": admin,
        "backend": telemetry.BACKEND,
        "db_enabled": db._enabled(),
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Analytics
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/api/summary")
async def api_summary(request: Request):
    _require_admin(request)
    days = _int_qp(request, "days", 14)
    data = db.get_summary(days)
    if not data:
        raise HTTPException(status_code=503, detail="Analytics database not configured")
    return data


@router.get("/api/timeseries")
async def api_timeseries(request: Request):
    _require_admin(request)
    metric = request.query_params.get("metric", "signups")
    days = _int_qp(request, "days", 14)
    return {"metric": metric, "days": days, "points": db.get_timeseries(metric, days)}


@router.get("/api/breakdown")
async def api_breakdown(request: Request):
    _require_admin(request)
    dim = request.query_params.get("dim", "frontend")
    days = _int_qp(request, "days", 14)
    kind = request.query_params.get("kind", "auth")
    if kind == "jobs":
        rows = db.get_jobs_breakdown(dim, days)
    else:
        rows = db.get_breakdown(dim, days, kind)
    return {"dim": dim, "days": days, "kind": kind, "rows": rows}


@router.get("/api/online")
async def api_online(request: Request):
    _require_admin(request)
    minutes = _int_qp(request, "minutes", 15)
    return {
        "minutes": minutes,
        **db.get_online_counts(),
        "users": db.get_online_users(minutes),
    }


@router.get("/api/latency")
async def api_latency(request: Request):
    _require_admin(request)
    days = _int_qp(request, "days", 14)
    return {"days": days, "points": db.get_latency_series(days)}


@router.get("/api/retention")
async def api_retention(request: Request):
    _require_admin(request)
    weeks = _int_qp(request, "weeks", 8)
    return {"weeks": weeks, "cohorts": db.get_retention(weeks)}


@router.get("/api/backends")
async def api_backends(request: Request):
    _require_admin(request)
    return {"backends": db.list_backends()}


# ─────────────────────────────────────────────────────────────────────────────
# Listings (paged, filterable)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/api/sessions")
async def api_sessions(request: Request):
    _require_admin(request)
    f = _filters(request, ["q", "frontend", "backend", "status", "days"])
    return db.list_auth_events(f, _int_qp(request, "page", 1), _int_qp(request, "per", 25))


@router.get("/api/requests")
async def api_requests(request: Request):
    _require_admin(request)
    f = _filters(request, ["q", "method", "status", "backend", "path", "min_status", "days"])
    return db.list_requests(f, _int_qp(request, "page", 1), _int_qp(request, "per", 25))


@router.get("/api/users")
async def api_users(request: Request):
    _require_admin(request)
    f = _filters(request, ["q", "days"])
    return db.list_users_paginated(f, _int_qp(request, "page", 1), _int_qp(request, "per", 25))


@router.get("/api/jobs")
async def api_jobs(request: Request):
    _require_admin(request)
    f = _filters(request, ["q", "status", "source_type", "user_id", "provider", "days"])
    return db.list_jobs_paginated(f, _int_qp(request, "page", 1), _int_qp(request, "per", 25))


@router.get("/api/events")
async def api_events(request: Request):
    _require_admin(request)
    f = _filters(request, ["q", "event_name", "user_id", "days"])
    return db.list_events_paginated(f, _int_qp(request, "page", 1), _int_qp(request, "per", 50))


@router.get("/api/logs")
async def api_logs(request: Request):
    _require_admin(request)
    f = _filters(request, ["q", "level", "backend", "days"])
    return db.list_server_logs(f, _int_qp(request, "page", 1), _int_qp(request, "per", 50))


@router.get("/api/audit")
async def api_audit(request: Request):
    _require_admin(request)
    f = _filters(request, ["q", "admin", "days"])
    return db.list_admin_audit(f, _int_qp(request, "page", 1), _int_qp(request, "per", 50))


# ─────────────────────────────────────────────────────────────────────────────
# Admin account management
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/api/admins")
async def api_admins(request: Request):
    admin = _require_admin(request)
    _audit(request, admin, "list_admins")
    return {"admins": db.list_admins()}


@router.post("/api/admins")
async def api_create_admin(request: Request, body: dict):
    admin = _require_admin(request)
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    ok = db.create_admin(username, password)
    if not ok:
        raise HTTPException(status_code=409, detail="Admin already exists (or bcrypt unavailable)")
    _audit(request, admin, "create_admin", username)
    return {"message": f"Admin {username} created"}


@router.delete("/api/admins/{username}")
async def api_delete_admin(request: Request, username: str):
    admin = _require_admin(request)
    if username == admin:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    ok = db.delete_admin(username)
    if not ok:
        raise HTTPException(status_code=400, detail="Cannot delete last admin or admin not found")
    _audit(request, admin, "delete_admin", username)
    return {"message": f"Admin {username} deleted"}


@router.post("/api/admins/{username}/password")
async def api_reset_admin_password(request: Request, username: str, body: dict):
    admin = _require_admin(request)
    password = str(body.get("password", ""))
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    ok = db.set_admin_password(username, password)
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to update password")
    _audit(request, admin, "reset_password", username)
    return {"message": f"Password updated for {username}"}


# ─────────────────────────────────────────────────────────────────────────────
# CSV export
# ─────────────────────────────────────────────────────────────────────────────

_EXPORTS = {
    "users": ("export_users", ["id", "email", "name", "display_name", "created_at", "last_login"]),
    "sessions": (
        "export_auth_events",
        ["id", "created_at", "user_id", "email", "provider", "status", "error", "is_new",
         "frontend", "frontend_origin", "backend_id", "backend_name", "instance_id",
         "ip", "country", "browser", "os", "device"],
    ),
    "requests": (
        "export_requests",
        ["id", "created_at", "backend_id", "instance_id", "method", "path", "status",
         "duration_ms", "ip", "user_id", "frontend", "frontend_origin", "browser", "os", "device"],
    ),
    "logs": (
        "export_server_logs",
        ["id", "created_at", "backend_id", "instance_id", "level", "logger", "filename",
         "lineno", "message", "exc_info"],
    ),
    "events": (
        "export_events",
        ["id", "created_at", "user_id", "event_name", "properties"],
    ),
    "jobs": (
        "export_jobs",
        ["job_id", "user_id", "user_email", "user_name", "source_type", "status",
         "video_title", "error", "ai_usage", "created_at", "updated_at"],
    ),
}


@router.get("/api/export/{kind}")
async def api_export(request: Request, kind: str):
    _require_admin(request)
    spec = _EXPORTS.get(kind)
    if not spec:
        raise HTTPException(status_code=404, detail="Unknown export kind")
    days = request.query_params.get("days")
    rows = getattr(db, spec[0])(int(days) if days else None)
    cols = spec[1]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(cols)
    for row in rows:
        writer.writerow([
            json.dumps(row.get(c)) if isinstance(row.get(c), (dict, list)) else row.get(c, "")
            for c in cols
        ])
    filename = f"clipo_{kind}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Legacy compatibility endpoints (keep old dashboard clients working)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/stats")
async def admin_stats(request: Request):
    _require_admin(request)
    stats = db.get_stats()
    if not stats:
        raise HTTPException(status_code=503, detail="Analytics database not configured")
    return stats


@router.get("/users")
async def admin_users(request: Request):
    _require_admin(request)
    return {"users": db.list_users(100)}


@router.get("/jobs")
async def admin_jobs(request: Request):
    _require_admin(request)
    return {"jobs": db.list_jobs(100)}


@router.get("/events")
async def admin_events(request: Request):
    _require_admin(request)
    return {"events": db.list_events(200)}


@router.get("/logs")
async def admin_logs(request: Request):
    _require_admin(request)
    return {"logs": db.list_logs(200)}


# ─────────────────────────────────────────────────────────────────────────────
# Panel serving — redirect to the SPA mounted at /admin/app/
# ─────────────────────────────────────────────────────────────────────────────

@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
async def admin_panel():
    return RedirectResponse(url="/admin/app/", status_code=302)
