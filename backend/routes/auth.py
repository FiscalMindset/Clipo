"""
Auth Routes — Google OAuth 2.0 login/logout/session.
"""

import json
import logging
import hashlib
import hmac
import secrets
import smtplib
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, quote
from email.message import EmailMessage

import httpx

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from jose import jwt, JWTError

from config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    FRONTEND_URLS,
    BACKEND_URL,
    JWT_SECRET,
    JWT_ALGORITHM,
    JWT_EXPIRE_HOURS,
    SESSION_COOKIE_SECRET,
    ENABLE_GOOGLE_AUTH,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASS,
    SMTP_USE_TLS,
)
from services.supabase_service import sync_user_to_supabase

router = APIRouter(prefix="/auth")
logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

COOKIE_NAME = "clipo_session"

_USERS_FILE = Path(__file__).resolve().parent.parent / "users.json"
PASSWORD_RESET_TTL_MINUTES = 30


def _load_users() -> dict[str, dict]:
    if _USERS_FILE.exists():
        raw = _USERS_FILE.read_text()
        if raw.strip():
            return json.loads(raw)
    return {}


def _save_users(users: dict[str, dict]) -> None:
    _USERS_FILE.write_text(json.dumps(users, indent=2, default=str))


def _find_user_by_email(email: str, users: dict[str, dict] | None = None) -> dict | None:
    users = users if users is not None else _load_users()
    email = email.strip().lower()
    return next((user for user in users.values() if user.get("email", "").lower() == email), None)


def _public_user(user: dict) -> dict:
    created_at = user["created_at"]
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "display_name": user.get("display_name", ""),
        "bio": user.get("bio", ""),
        "picture": user.get("picture", ""),
        "created_at": created_at,
    }


def _hash_password(password: str) -> str:
    """Hash a password with scrypt (available in Python's standard library)."""
    salt = secrets.token_bytes(16)
    n, r, p = 2**14, 8, 1
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p)
    return f"scrypt${n}${r}${p}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_hex, expected_hex = encoded.split("$", 6)
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
            n=int(n), r=int(r), p=int(p),
        )
        return hmac.compare_digest(actual, bytes.fromhex(expected_hex))
    except (TypeError, ValueError):
        return False


def _session_response(user: dict) -> JSONResponse:
    token = _create_jwt(user["id"], user["email"], user["name"], user.get("picture", ""))
    response = JSONResponse(content={"user": _public_user(user), "token": token})
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=BACKEND_URL.startswith("https://"),
        samesite="none" if BACKEND_URL.startswith("https://") else "lax",
        max_age=JWT_EXPIRE_HOURS * 3600,
        path="/",
    )
    return response


def _send_reset_email(email: str, name: str, token: str) -> bool:
    """Send a reset link when SMTP is configured; never expose reset tokens in API responses."""
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASS:
        logger.warning("Password reset requested for %s but SMTP is not configured", email)
        return False
    reset_url = f"{FRONTEND_URL.rstrip('/')}/?reset_token={quote(token, safe='')}"
    message = EmailMessage()
    message["Subject"] = "Reset your Clipo password"
    message["From"] = SMTP_USER
    message["To"] = email
    message.set_content(
        f"Hi {name or 'there'},\n\nReset your Clipo password within {PASSWORD_RESET_TTL_MINUTES} minutes:\n{reset_url}\n"
    )
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as client:
        if SMTP_USE_TLS:
            client.starttls()
        client.login(SMTP_USER, SMTP_PASS)
        client.send_message(message)
    return True


def _create_jwt(user_id: str, email: str, name: str, picture: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "name": name,
        "picture": picture,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_jwt(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


def get_current_user(request: Request) -> dict | None:
    """Extract current user from session cookie OR Authorization Bearer token.

    Returns None if unauthenticated.
    """
    token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    payload = _decode_jwt(token)
    if not payload:
        return None
    user_id = payload.get("sub")
    users = _load_users()
    if not user_id or user_id not in users:
        return None
    return users[user_id]


def require_user(request: Request) -> dict:
    """Like get_current_user but raises 401 if not authenticated."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# ─────────────────────────────────────────────────────────────────────────────
# Sign-in telemetry (which frontend + which backend + IP + UA)
# ─────────────────────────────────────────────────────────────────────────────

def _auth_context(request: Request, origin: str) -> dict:
    """Build the context dict recorded with every auth event."""
    from config import frontend_name
    from services import telemetry

    ctx = telemetry.client_context(request)
    # The OAuth `state` origin is authoritative for "which frontend started
    # this sign-in" (the Origin/Referer header is Google's on the callback).
    ctx["frontend_origin"] = origin
    ctx["frontend"] = frontend_name(origin)
    ctx["backend_id"] = telemetry.BACKEND["backend_id"]
    ctx["backend_name"] = telemetry.BACKEND["name"]
    ctx["instance_id"] = telemetry.BACKEND["instance_id"]
    return ctx


def record_auth(
    request: Request,
    origin: str,
    status: str,
    *,
    user_id: str | None = None,
    email: str | None = None,
    error: str | None = None,
    is_new: bool | None = None,
) -> None:
    """Fire-and-forget auth event write (never raises into the request path)."""
    try:
        from services import db as _db
        _db.record_auth_event(
            user_id, email, status, error=error,
            context=_auth_context(request, origin), is_new=is_new,
        )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/google")
async def google_login(state: str = None):
    """Redirect to Google's OAuth consent screen.

    The `state` query param records which frontend origin started the login so
    the callback can redirect the user back to that origin. Defaults to the
    first configured frontend URL.
    """
    if not ENABLE_GOOGLE_AUTH:
        raise HTTPException(status_code=404, detail="Google sign-in is temporarily disabled")
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")

    origin = FRONTEND_URLS[0]
    if state and state in FRONTEND_URLS:
        origin = state

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": f"{BACKEND_URL}/auth/google/callback",
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
        "state": origin,
    }
    return RedirectResponse(url=f"{GOOGLE_AUTH_URL}?{urlencode(params)}")


@router.get("/google/callback")
async def google_callback(request: Request, code: str = None, error: str = None, state: str = None):
    """Exchange Google auth code for tokens, create session, redirect to app."""
    if not ENABLE_GOOGLE_AUTH:
        raise HTTPException(status_code=404, detail="Google sign-in is temporarily disabled")
    origin = state if (state and state in FRONTEND_URLS) else FRONTEND_URLS[0]
    if error:
        record_auth(request, origin, "failed", error=f"oauth_error:{error}")
        return RedirectResponse(url=f"{origin}?error={error}")
    if not code:
        record_auth(request, origin, "failed", error="no_code")
        return RedirectResponse(url=f"{origin}?error=no_code")

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": f"{BACKEND_URL}/auth/google/callback",
                "grant_type": "authorization_code",
            },
            timeout=10,
        )

    if token_resp.status_code != 200:
        record_auth(request, origin, "failed", error="token_exchange_failed")
        return RedirectResponse(url=f"{origin}?error=token_exchange_failed")

    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        record_auth(request, origin, "failed", error="no_access_token")
        return RedirectResponse(url=f"{origin}?error=no_access_token")

    # Fetch user info from Google
    async with httpx.AsyncClient() as client:
        userinfo_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )

    if userinfo_resp.status_code != 200:
        record_auth(request, origin, "failed", error="userinfo_failed")
        return RedirectResponse(url=f"{origin}?error=userinfo_failed")

    info = userinfo_resp.json()
    google_id = info["sub"]
    email = info.get("email", "")
    name = info.get("name", "")
    picture = info.get("picture", "")
    now = datetime.now(timezone.utc)

    # Upsert user with persistence
    users = _load_users()
    existing = users.get(google_id, {})
    user = {
        "id": google_id,
        "email": email,
        "name": name,
        "display_name": existing.get("display_name", ""),
        "bio": existing.get("bio", ""),
        "picture": picture,
        "created_at": existing.get("created_at", now),
        "last_login": now,
    }
    users[google_id] = user
    _save_users(users)

    try:
        synced = await sync_user_to_supabase(user)
        if not synced:
            logger.warning("Supabase sync skipped or failed for user %s", google_id)
    except Exception as exc:  # noqa: BLE001 - login should still succeed locally
        logger.warning("Supabase sync failed for user %s: %s", google_id, exc)

    # Mirror the user into Postgres analytics (no-op when DB not configured).
    is_new = False
    try:
        from services import db as _db
        is_new = _db.upsert_user(user)
        _db.record_event(google_id, "login", {"email": email, "is_new": is_new})
    except Exception:
        pass

    # Record the full sign-in context: which frontend, which backend, IP, UA.
    record_auth(request, origin, "success", user_id=google_id, email=email, is_new=is_new)

    # Create JWT session
    token = _create_jwt(google_id, email, name, picture)

    # Set cookie and redirect.
    is_https = origin.startswith("https")
    # Cross-origin production (frontend and backend on different hosts) requires
    # SameSite=None + Secure, otherwise the browser drops the cookie on API calls.
    _same_site = "none" if is_https else "lax"
    # The cookie alone is unreliable across origins (third-party cookie blocking),
    # so we also hand the JWT to the frontend via the URL fragment. The frontend
    # stores it in localStorage and sends it as an Authorization: Bearer header.
    callback_path = origin.rstrip("/") + "/auth/callback#token=" + quote(token, safe="")
    response = RedirectResponse(url=callback_path, status_code=302)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=is_https,
        samesite=_same_site,
        max_age=JWT_EXPIRE_HOURS * 3600,
        path="/",
    )
    return response


@router.post("/signup")
async def signup(body: dict):
    """Create an email/password account and begin an authenticated session."""
    name = str(body.get("name", "")).strip()
    email = str(body.get("email", "")).strip().lower()
    password = str(body.get("password", ""))
    if not name or "@" not in email:
        raise HTTPException(status_code=400, detail="Enter a valid name and email address")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    users = _load_users()
    if _find_user_by_email(email, users):
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user_id = f"email_{secrets.token_urlsafe(18)}"
    now = datetime.now(timezone.utc)
    user = {
        "id": user_id,
        "email": email,
        "name": name,
        "display_name": "",
        "bio": "",
        "picture": "",
        "created_at": now,
        "last_login": now,
        "auth_provider": "password",
        "password_hash": _hash_password(password),
    }
    users[user_id] = user
    _save_users(users)
    return _session_response(user)


@router.post("/login")
async def login(body: dict):
    """Authenticate an existing email/password account."""
    email = str(body.get("email", "")).strip().lower()
    password = str(body.get("password", ""))
    user = _find_user_by_email(email)
    password_hash = user.get("password_hash", "") if user else ""
    if not user or not password_hash or not _verify_password(password, password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    users = _load_users()
    users[user["id"]]["last_login"] = datetime.now(timezone.utc)
    _save_users(users)
    return _session_response(users[user["id"]])


@router.post("/forgot-password")
async def forgot_password(body: dict):
    """Start a password reset without revealing whether an email is registered."""
    email = str(body.get("email", "")).strip().lower()
    users = _load_users()
    user = _find_user_by_email(email, users)
    if user and user.get("password_hash"):
        token = secrets.token_urlsafe(32)
        user["password_reset_hash"] = hashlib.sha256(token.encode("utf-8")).hexdigest()
        user["password_reset_expires_at"] = (datetime.now(timezone.utc) + timedelta(minutes=PASSWORD_RESET_TTL_MINUTES)).isoformat()
        _save_users(users)
        try:
            _send_reset_email(user["email"], user.get("name", ""), token)
        except Exception as exc:  # Do not expose mail configuration details to clients.
            logger.exception("Could not send password reset email: %s", exc)
    return {"message": "If an account exists for that email, a reset link has been sent."}


@router.post("/reset-password")
async def reset_password(body: dict):
    token = str(body.get("token", ""))
    password = str(body.get("password", ""))
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc)
    users = _load_users()
    user = next((candidate for candidate in users.values() if candidate.get("password_reset_hash") == token_hash), None)
    if not user:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired")
    try:
        expires_at = datetime.fromisoformat(user["password_reset_expires_at"])
        if expires_at <= now:
            raise ValueError
    except (KeyError, ValueError):
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired")
    user["password_hash"] = _hash_password(password)
    user.pop("password_reset_hash", None)
    user.pop("password_reset_expires_at", None)
    _save_users(users)
    return {"message": "Password updated. You can now log in."}


@router.get("/me")
async def get_me(request: Request):
    """Return the currently authenticated user, or 401."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return _public_user(user)


@router.put("/profile")
async def update_profile(request: Request, body: dict):
    """Update display name and bio for the authenticated user."""
    user = require_user(request)
    users = _load_users()
    uid = user["id"]

    if "display_name" in body:
        users[uid]["display_name"] = body["display_name"][:60]
    if "bio" in body:
        users[uid]["bio"] = body["bio"][:300]

    _save_users(users)
    return {"message": "Profile updated"}


@router.get("/stats")
async def get_stats(request: Request):
    """Return usage statistics for the authenticated user."""
    user = require_user(request)

    from services.pipeline_service import jobs, get_user_jobs
    from config import CLIP_DIR
    from models.schemas import JobStatus

    uid = user["id"]
    user_jobs = get_user_jobs(uid)

    total_jobs = len(user_jobs)
    total_clips = 0
    completed_jobs = 0
    total_storage = 0

    for jid in user_jobs:
        job = jobs[jid]
        clips = job.get("clips", [])
        total_clips += len(clips)
        if job.get("status") == JobStatus.COMPLETED:
            completed_jobs += 1
            for c in clips:
                fpath = CLIP_DIR / jid / c["filename"]
                if fpath.exists():
                    total_storage += fpath.stat().st_size

    return {
        "total_jobs": total_jobs,
        "completed_jobs": completed_jobs,
        "total_clips": total_clips,
        "storage_bytes": total_storage,
        "storage_mb": round(total_storage / (1024 * 1024), 1),
    }


@router.post("/logout")
async def logout(request: Request):
    """Clear the session cookie."""
    user = get_current_user(request)
    if user:
        try:
            from services import db as _db
            _db.record_event(user["id"], "logout", {})
        except Exception:
            pass
    response = JSONResponse(content={"message": "Logged out"})
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return response
