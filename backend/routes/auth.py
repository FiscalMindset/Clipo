"""
Auth Routes — Google OAuth 2.0 login/logout/session.
"""

import httpx
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from jose import jwt, JWTError

from config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    FRONTEND_URL,
    BACKEND_URL,
    JWT_SECRET,
    JWT_ALGORITHM,
    JWT_EXPIRE_HOURS,
    SESSION_COOKIE_SECRET,
)

router = APIRouter(prefix="/auth")

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

COOKIE_NAME = "clipo_session"

# In-memory user store (swap for DB if persistence needed)
users: dict[str, dict] = {}


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
    """Extract current user from session cookie. Returns None if unauthenticated."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    payload = _decode_jwt(token)
    if not payload:
        return None
    user_id = payload.get("sub")
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
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/google")
async def google_login():
    """Redirect to Google's OAuth consent screen."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": f"{BACKEND_URL}/auth/google/callback",
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
    }
    return RedirectResponse(url=f"{GOOGLE_AUTH_URL}?{urlencode(params)}")


@router.get("/google/callback")
async def google_callback(code: str = None, error: str = None):
    """Exchange Google auth code for tokens, create session, redirect to app."""
    if error:
        return RedirectResponse(url=f"{FRONTEND_URL}?error={error}")
    if not code:
        return RedirectResponse(url=f"{FRONTEND_URL}?error=no_code")

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
        return RedirectResponse(url=f"{FRONTEND_URL}?error=token_exchange_failed")

    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        return RedirectResponse(url=f"{FRONTEND_URL}?error=no_access_token")

    # Fetch user info from Google
    async with httpx.AsyncClient() as client:
        userinfo_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )

    if userinfo_resp.status_code != 200:
        return RedirectResponse(url=f"{FRONTEND_URL}?error=userinfo_failed")

    info = userinfo_resp.json()
    google_id = info["sub"]
    email = info.get("email", "")
    name = info.get("name", "")
    picture = info.get("picture", "")

    # Upsert user
    user = {
        "id": google_id,
        "email": email,
        "name": name,
        "picture": picture,
        "created_at": users.get(google_id, {}).get("created_at", datetime.now(timezone.utc)),
        "last_login": datetime.now(timezone.utc),
    }
    users[google_id] = user

    # Create JWT session
    token = _create_jwt(google_id, email, name, picture)

    # Set cookie and redirect
    is_https = FRONTEND_URL.startswith("https")
    response = RedirectResponse(url=f"{FRONTEND_URL}", status_code=302)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=is_https,
        samesite="lax",
        max_age=JWT_EXPIRE_HOURS * 3600,
        path="/",
    )
    return response


@router.get("/me")
async def get_me(request: Request):
    """Return the currently authenticated user, or 401."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "picture": user["picture"],
    }


@router.post("/logout")
async def logout():
    """Clear the session cookie."""
    response = JSONResponse(content={"message": "Logged out"})
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return response
