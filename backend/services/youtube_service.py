"""
YouTube Service — downloads YouTube videos via yt-dlp.
Uses subprocess.run in a thread executor for Windows compatibility.
"""

import re
import asyncio
import json
import logging
import subprocess
import functools
import sys
from pathlib import Path
from fastapi import HTTPException

logger = logging.getLogger(__name__)

# Set once the first time strategies are built, so each instance reports in
# server_logs whether an operator-supplied cookies.txt is active.
_cookies_logged = False

from config import UPLOAD_DIR, MAX_YOUTUBE_DURATION, YOUTUBE_COOKIES_FILE, POT_PROVIDER_BASE_URL


YOUTUBE_URL_PATTERN = re.compile(
    r"(https?://)?(www\.|m\.)?"
    r"(youtube\.com/(watch\?v=|shorts/|embed/|live/|v/)|youtu\.be/)"
    r"[\w\-]+"
)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"


def validate_youtube_url(url: str) -> str:
    """Validate that the URL is a valid YouTube URL."""
    url = url.strip()
    if not YOUTUBE_URL_PATTERN.match(url):
        raise HTTPException(
            status_code=400,
            detail="Invalid YouTube URL. Please provide a valid youtube.com or youtu.be link."
        )
    return url


_UA_ARG = ["--user-agent", _UA]


def _yt_dlp_strategies() -> list[list[str]]:
    """
    Ordered list of yt-dlp extra-argument sets to try per request.

    YouTube throws a "Sign in to confirm you're not a bot" wall on datacenter
    IPs (Azure) regardless of client or TLS fingerprint. Two things make a
    request look like a real browser and get past it:

    * TLS impersonation: ``--impersonate`` (backed by curl_cffi) makes every
      request carry a genuine Chrome/Safari fingerprint and HTTP/2 behaviour.
    * A proof-of-origin token: the bundled bgutil HTTP server (see
      POT_PROVIDER_BASE_URL) mints a PO token for the ``web`` player, which is
      po_token-gated in current YouTube builds.

    Strategy order, most reliable first:
      1. Impersonated Chrome on the ``web`` player with a PO token — the
         primary automatic path for flagged IPs. yt-dlp pulls the token from
         the local bgutil server (port 4416) via the bgutil-ytdlp-pot-provider
         plugin.
      2. The same PO-token path across more player clients.
      3. An operator-supplied cookies.txt (via env secret) — the most reliable
         bypass. It is tried right after the automatic PO-token path so it only
         serves videos the token cannot get past (the PO-token path does not
         always bypass YouTube's per-video bot check).
      4. Impersonated Chrome on android_vr/tv_embedded/… — these embedded and
         VR players return usable formats without a po_token where the wall is
         not enforced (they still pass through impersonation).
      5. Impersonated Chrome on ``web`` without a PO token (works where the
         wall is not enforced).
      6. Impersonated Safari on tv_embedded/web_safari.
      7. Impersonated Chrome on the default client — fast path.
      8. Browser-cookie strategies (only useful when a real browser profile
         is present, e.g. local dev).
      9. Legacy client swaps without impersonation.
    The first strategy that succeeds wins; if all fail we surface the last error.

    Every strategy also enables ``--remote-components ejs:github``. Recent
    YouTube builds require solving JS challenges (signature + n-parameter);
    yt-dlp needs a JavaScript runtime (deno/node, installed in the Docker
    image) plus its EJS solver-script distribution, which is downloaded from
    GitHub and cached. Without this, only images resolve and the format
    request fails.
    """
    global _cookies_logged
    base = ["--remote-components", "ejs:github"]
    chrome = ["--impersonate", "chrome"]
    strategies: list[list[str]] = []
    pot = []
    if POT_PROVIDER_BASE_URL:
        pot = ["--extractor-args", f"youtubepot-bgutilhttp:base_url={POT_PROVIDER_BASE_URL}"]
    cookies = []
    if YOUTUBE_COOKIES_FILE:
        try:
            if Path(YOUTUBE_COOKIES_FILE).is_file() and Path(YOUTUBE_COOKIES_FILE).stat().st_size > 0:
                cookies = ["--cookies", YOUTUBE_COOKIES_FILE]
        except OSError:
            cookies = []
    if not _cookies_logged:
        _cookies_logged = True
        if cookies:
            logger.info("yt-dlp cookies: using %s", YOUTUBE_COOKIES_FILE)
        else:
            logger.info("yt-dlp cookies: none configured")
    if pot:
        strategies.extend([
            [*base, *chrome, *pot, "--extractor-args", "youtube:player_client=web"],
            [*base, *chrome, *pot, "--extractor-args", "youtube:player_client=web,tv_embedded,mweb,web_embedded"],
        ])
    if cookies:
        strategies.extend([
            [*base, *chrome, *cookies],
            [*base, *chrome, *pot, *cookies, "--extractor-args", "youtube:player_client=web"],
            [*base, *cookies],
        ])
    strategies.extend([
        [*base, *chrome, "--extractor-args", "youtube:player_client=android_vr,tv_embedded,web_embedded,android,mweb,tv,web_safari"],
        [*base, *chrome, "--extractor-args", "youtube:player_client=android_vr,tv_embedded"],
        [*base, *chrome, "--extractor-args", "youtube:player_client=web"],
        [*base, "--impersonate", "safari", "--extractor-args", "youtube:player_client=tv_embedded,web_safari"],
        [*base, *chrome],
        [*base, "--cookies-from-browser", "chrome"],
        [*base, "--cookies-from-browser", "edge"],
        [*base, "--cookies-from-browser", "brave"],
        [*base, "--extractor-args", "youtube:player_client=tv"],
        [*base, "--extractor-args", "youtube:player_client=android_vr"],
        [*base, "--extractor-args", "youtube:player_client=mweb"],
        [*base, "--extractor-args", "youtube:player_client=web_embedded"],
        [*base, "--extractor-args", "youtube:player_client=tv,android_vr,web_embedded,mweb"],
        [*base, "--extractor-args", "youtube:player_client=tv,web_safari,ios"],
    ])
    strategies.append([*base])
    return strategies


def _bot_wall_hint(last_err: str) -> str:
    """Append an actionable hint when yt-dlp hit YouTube's bot verification."""
    if not last_err or ("Sign in" not in last_err and "not a bot" not in last_err):
        return last_err
    return (
        f"{last_err}\n\n"
        "YouTube's bot check is triggered by the server's IP address. Downloads "
        "already retry automatically with browser impersonation and alternate "
        "player clients, so no action is needed from you. If this keeps failing "
        "the hosting IP is flagged by Google — it typically clears on its own, "
        "and a clean proxy unblocks it permanently."
    )


def _yt_dlp_command(*args: str) -> list[str]:
    """Run yt-dlp from the same Python environment as the backend.

    Invoking the module avoids relying on a globally installed ``yt-dlp``
    executable, which is especially important on Windows virtual environments.
    """
    return [sys.executable, "-m", "yt_dlp", *args]


def _get_video_info_sync(url: str) -> dict:
    """Fetch video metadata without downloading (sync, runs in executor)."""
    last_err = "No yt-dlp strategies succeeded"
    for idx, extra in enumerate(_yt_dlp_strategies()):
        try:
            result = subprocess.run(
                _yt_dlp_command(*extra, "--dump-json", "--no-download", "--no-warnings", url),
                capture_output=True,
                text=True,
                timeout=180,
            )
            if result.returncode == 0 and result.stdout.strip():
                logger.info("yt-dlp info: strategy %d OK for %s", idx, url)
                return json.loads(result.stdout)
            last_err = result.stderr.strip()
            logger.warning(
                "yt-dlp info: strategy %d failed for %s: %s",
                idx, url, last_err[-300:],
            )
        except Exception as exc:  # noqa: BLE001 - fall through to next strategy
            last_err = str(exc)
            logger.warning("yt-dlp info: strategy %d error for %s: %s", idx, url, exc)
    raise RuntimeError(f"Failed to fetch video info: {_bot_wall_hint(last_err)}")


def _download_video_sync(url: str, output_path: str) -> None:
    """Download video using yt-dlp (sync, runs in executor)."""
    last_err = "No yt-dlp strategies succeeded"
    for idx, extra in enumerate(_yt_dlp_strategies()):
        try:
            result = subprocess.run(
                _yt_dlp_command(
                    *extra,
                    "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                    "--merge-output-format", "mp4",
                    "-o", output_path,
                    "--no-playlist",
                    "--no-warnings",
                    url,
                ),
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout for large videos
            )
            if result.returncode == 0:
                logger.info("yt-dlp download: strategy %d OK for %s", idx, url)
                return
            last_err = result.stderr.strip()
            logger.warning(
                "yt-dlp download: strategy %d failed for %s: %s",
                idx, url, last_err[-300:],
            )
        except Exception as exc:  # noqa: BLE001 - fall through to next strategy
            last_err = str(exc)
            logger.warning("yt-dlp download: strategy %d error for %s: %s", idx, url, exc)
    raise RuntimeError(f"Failed to download video: {_bot_wall_hint(last_err)}")


async def get_video_info(url: str) -> dict:
    """Fetch video metadata without downloading."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, functools.partial(_get_video_info_sync, url)
    )


async def download_video(url: str, job_id: str) -> tuple[Path, str]:
    """
    Download a YouTube video using yt-dlp.
    Returns (file_path, video_title).
    """
    url = validate_youtube_url(url)

    # Get video info first to check duration
    info = await get_video_info(url)
    duration = info.get("duration", 0)
    title = info.get("title", "YouTube Video")

    if duration > MAX_YOUTUBE_DURATION:
        hours = MAX_YOUTUBE_DURATION // 3600
        raise HTTPException(
            status_code=400,
            detail=f"Video is too long ({duration // 60} min). Maximum allowed is {hours} hours."
        )

    output_path = UPLOAD_DIR / f"{job_id}.mp4"

    # Download in executor
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None, functools.partial(_download_video_sync, url, str(output_path))
    )

    if not output_path.exists():
        raise RuntimeError("Download completed but file not found.")

    return output_path, title
