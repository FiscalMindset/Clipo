"""Supabase sync helpers for Clipo AI."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from config import SUPABASE_ANON_KEY, SUPABASE_URL, SUPABASE_USERS_TABLE


logger = logging.getLogger(__name__)


def _format_timestamp(value: object) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


async def sync_user_to_supabase(user: dict) -> bool:
    """Mirror a logged-in user into Supabase.

    Returns True when Supabase accepted the write, False when sync is disabled
    or the request failed.
    """
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        logger.info("Supabase sync disabled because credentials are missing")
        return False

    payload = {
        "id": user.get("id", ""),
        "email": user.get("email", ""),
        "name": user.get("name", ""),
        "display_name": user.get("display_name", ""),
        "bio": user.get("bio", ""),
        "picture": user.get("picture", ""),
        "created_at": _format_timestamp(user.get("created_at", datetime.now(timezone.utc))),
        "last_login": _format_timestamp(user.get("last_login", datetime.now(timezone.utc))),
    }

    base_url = SUPABASE_URL.rstrip("/")
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "content-type": "application/json",
        "prefer": "resolution=merge-duplicates,return=minimal",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"{base_url}/rest/v1/{SUPABASE_USERS_TABLE}",
            params={"on_conflict": "id"},
            headers=headers,
            json=payload,
        )

    if response.status_code not in {200, 201, 204}:
        logger.warning("Supabase sync failed: %s %s", response.status_code, response.text)
        return False

    return True