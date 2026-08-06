"""
External YouTube download worker.

The Azure backend's IP is flagged by Google, so some videos hit the "Sign in
to confirm you're not a bot" wall no matter what client or token the server
uses. Those jobs are parked in ``WAITING_WORKER`` state and this script —
running from an unflagged IP (e.g. the operator's home machine) — downloads
the video with the same yt-dlp strategy stack and uploads it back to the
backend, which then resumes the pipeline (whisper / AI / clips stay
server-side).

Usage (from backend/):
    WORKER_TOKEN=<shared-secret> WORKER_API_BASE=https://<backend> python worker_downloader.py

Reuses the backend's own config and services, so run it with this repo's
virtualenv (it needs yt-dlp + curl_cffi for the impersonation strategies).
"""

import asyncio
import os
import sys
from pathlib import Path

import httpx

from config import WORKER_TOKEN, UPLOAD_DIR
from services.youtube_service import download_video


WORKER_API_BASE = os.getenv("WORKER_API_BASE", "").strip()
POLL_SECONDS = int(os.getenv("WORKER_POLL_SECONDS", "30"))


async def _process_job(client: httpx.AsyncClient, job: dict) -> None:
    job_id = job["job_id"]
    url = job["youtube_url"]
    print(f"[worker] downloading {job_id} :: {url}", flush=True)
    path: Path | None = None
    try:
        path, title = await download_video(url, job_id)
        print(f"[worker] downloaded {job_id} ({path.stat().st_size / 1_048_576:.1f} MB)", flush=True)

        with path.open("rb") as fh:
            resp = await client.post(
                f"/api/worker/upload/{job_id}",
                files={"file": (path.name, fh, "video/mp4")},
            )
        print(f"[worker] upload {job_id}: {resp.status_code} {resp.text[:200]}", flush=True)
    except Exception as exc:  # noqa: BLE001 - keep the loop alive; retry next poll
        print(f"[worker] failed {job_id}: {exc}", flush=True)
    finally:
        if path and path.exists():
            path.unlink(missing_ok=True)


async def main() -> None:
    if not WORKER_TOKEN:
        print("[worker] WORKER_TOKEN is not set — refusing to run.", flush=True)
        sys.exit(1)
    base = WORKER_API_BASE or os.getenv("BACKEND_URL", "http://localhost:8001").rstrip("/")
    print(f"[worker] polling {base} every {POLL_SECONDS}s", flush=True)

    headers = {"X-Worker-Token": WORKER_TOKEN}
    async with httpx.AsyncClient(base_url=base, headers=headers, timeout=httpx.Timeout(60 * 15, connect=30)) as client:
        while True:
            try:
                resp = await client.get("/api/worker/pending")
                if resp.status_code == 200:
                    jobs = (resp.json() or {}).get("jobs", [])
                    if jobs:
                        print(f"[worker] {len(jobs)} job(s) pending", flush=True)
                        for job in jobs:
                            await _process_job(client, job)
                else:
                    print(f"[worker] pending poll failed: {resp.status_code} {resp.text[:200]}", flush=True)
            except Exception as exc:  # noqa: BLE001 - transient network blips
                print(f"[worker] poll error: {exc}", flush=True)
            await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[worker] stopped.", flush=True)
