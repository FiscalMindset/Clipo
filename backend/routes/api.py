"""
API Routes for Clipo AI.
"""

import asyncio
import tempfile
import zipfile
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
import subprocess

from config import CLIP_DIR
from models.schemas import (
    UploadResponse,
    YouTubeRequest,
    ProcessingStatus,
    ClipInfo,
    JobStatus,
    StepInfo,
)
from services.upload_service import save_upload
from services.youtube_service import validate_youtube_url
from services.pipeline_service import (
    create_job,
    get_job,
    get_processing_status,
    run_pipeline,
    get_user_jobs,
    jobs,
)
from services.caption_service import generate_captioned_clip, list_styles
from routes.auth import get_current_user, require_user


router = APIRouter(prefix="/api")


@router.get("/health")
async def health_check():
    """Check if the backend is running and healthy."""
    from config import GEMINI_API_KEY, NVIDIA_API_KEY, AI_PROVIDER

    if AI_PROVIDER == "nvidia" or (not AI_PROVIDER and NVIDIA_API_KEY):
        provider = "nvidia"
        configured = bool(NVIDIA_API_KEY)
    elif GEMINI_API_KEY:
        provider = "gemini"
        configured = bool(GEMINI_API_KEY)
    else:
        provider = "none"
        configured = False

    return {
        "status": "ok",
        "ai_provider": provider,
        "ai_configured": configured,
        "gemini_configured": bool(GEMINI_API_KEY),
        "nvidia_configured": bool(NVIDIA_API_KEY),
    }


@router.get("/config")
async def get_config():
    """Return public config info the frontend needs."""
    from config import (
        GEMINI_API_KEY, NVIDIA_API_KEY, AI_PROVIDER,
        GEMINI_MODEL, NVIDIA_NIM_MODEL,
        MAX_UPLOAD_SIZE_GB, MAX_YOUTUBE_DURATION, MIN_CLIP_DURATION, MAX_CLIP_DURATION,
    )

    if AI_PROVIDER == "nvidia" or (not AI_PROVIDER and NVIDIA_API_KEY):
        active_provider = "nvidia"
    elif GEMINI_API_KEY:
        active_provider = "gemini"
    else:
        active_provider = "none"

    return {
        "ai_provider": active_provider,
        "gemini_configured": bool(GEMINI_API_KEY),
        "nvidia_configured": bool(NVIDIA_API_KEY),
        "gemini_model": GEMINI_MODEL,
        "nvidia_model": NVIDIA_NIM_MODEL,
        "max_upload_gb": MAX_UPLOAD_SIZE_GB,
        "max_youtube_duration_s": MAX_YOUTUBE_DURATION,
        "min_clip_duration": MIN_CLIP_DURATION,
        "max_clip_duration": MAX_CLIP_DURATION,
    }


@router.post("/upload", response_model=UploadResponse)
async def upload_video(request: Request, file: UploadFile = File(...)):
    """Upload a video file and create a processing job."""
    user = get_current_user(request)
    user_id = user["id"] if user else None

    job_id, file_path = await save_upload(file)

    create_job(
        job_id,
        source_type="file",
        video_path=str(file_path),
        video_title=file.filename,
        user_id=user_id,
    )

    return UploadResponse(
        job_id=job_id,
        filename=file.filename,
        status=JobStatus.PENDING,
    )


@router.post("/youtube", response_model=UploadResponse)
async def submit_youtube_url(req: Request, request: YouTubeRequest):
    """Accept a YouTube URL and create a processing job."""
    user = get_current_user(req)
    user_id = user["id"] if user else None

    url = validate_youtube_url(request.url)

    # Generate job ID
    import uuid
    job_id = uuid.uuid4().hex[:12]

    create_job(
        job_id,
        source_type="youtube",
        youtube_url=url,
        video_title="YouTube Video",
        user_id=user_id,
    )

    return UploadResponse(
        job_id=job_id,
        filename="YouTube Video",
        status=JobStatus.PENDING,
    )


@router.post("/generate/{job_id}")
async def start_processing(request: Request, job_id: str):
    """Trigger the processing pipeline for a job."""
    user = get_current_user(request)
    user_id = user["id"] if user else None

    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if user_id and job.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    if job["status"] not in (JobStatus.PENDING,):
        raise HTTPException(
            status_code=400,
            detail=f"Job is already {job['status'].value}. Cannot start again."
        )

    from main import whisper_model

    # Launch pipeline as a background task. The transcription service will
    # use the local model when available and fall back to Gemini otherwise.
    asyncio.create_task(run_pipeline(job_id, whisper_model))

    return {"message": "Processing started", "job_id": job_id}


@router.get("/status/{job_id}", response_model=ProcessingStatus)
async def get_status(request: Request, job_id: str):
    """Get current processing status for a job."""
    user = get_current_user(request)
    user_id = user["id"] if user else None

    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if user_id and job.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    status = get_processing_status(job_id)
    return status


@router.get("/jobs", response_model=list[ProcessingStatus])
async def get_jobs(request: Request):
    """Get all processing jobs for the current user (or all if unauthenticated)."""
    user = get_current_user(request)
    user_id = user["id"] if user else None

    result = []
    for jid in get_user_jobs(user_id):
        status = get_processing_status(jid)
        if status:
            result.append(status)
    result.sort(key=lambda x: x["created_at"], reverse=True)
    return result


@router.get("/clips/{job_id}", response_model=list[ClipInfo])
async def get_clips(request: Request, job_id: str):
    """Get all generated clips for a job."""
    user = get_current_user(request)
    user_id = user["id"] if user else None

    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if user_id and job.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    if job["status"] != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Job is not completed yet. Current status: {job['status'].value}"
        )

    return [ClipInfo(**c) for c in job["clips"]]


@router.get("/caption-styles")
async def caption_styles():
    """List available caption style variations."""
    return list_styles()


@router.post("/captions/{job_id}/{clip_id}")
async def create_captions(request: Request, job_id: str, clip_id: int, style: str = "classic"):
    """
    Burn word-level captions into a clip using the requested style.

    On-demand and additive: the original clip is untouched and the captioned
    version is returned separately. No AI call is made.
    """
    user = get_current_user(request)
    user_id = user["id"] if user else None

    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if user_id and job.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    if job["status"] != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Job is not completed yet. Current status: {job['status'].value}"
        )

    clip = next((c for c in job["clips"] if c["id"] == clip_id), None)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    try:
        result = generate_captioned_clip(job_id, clip_id, style)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Point the clip at the captioned file so the frontend just swaps the URL.
    clip["filename"] = result.filename
    clip["video_url"] = result.video_url

    return ClipInfo(**clip)


@router.get("/download/{job_id}/{filename}")
async def download_clip(request: Request, job_id: str, filename: str, aspect_ratio: str | None = None):
    """Download a specific clip file.

    Optional query param `aspect_ratio` can be `16:9` or `9:16`. When provided
    the server will transcode the stored clip to the requested aspect ratio and
    return a temporary MP4 file. The temporary file is removed after the
    response is finished.
    """
    clip_path = CLIP_DIR / job_id / filename

    if not clip_path.exists():
        raise HTTPException(status_code=404, detail="Clip not found")

    # Security: ensure the path doesn't escape the clips directory
    try:
        clip_path.resolve().relative_to(CLIP_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    # If no aspect requested, return original file
    if not aspect_ratio:
        return FileResponse(path=str(clip_path), filename=filename, media_type="video/mp4")

    # Validate aspect
    if aspect_ratio not in ("16:9", "9:16"):
        raise HTTPException(status_code=422, detail="Unsupported aspect_ratio; use 16:9 or 9:16")

    # Map to target resolution (use modest defaults to keep transcodes fast)
    if aspect_ratio == "16:9":
        target_w, target_h = 1280, 720
    else:
        target_w, target_h = 720, 1280

    # Create a temporary output file
    tmp = tempfile.NamedTemporaryFile(prefix=f"clipo-{job_id}-", suffix=".mp4", delete=False)
    out_path = Path(tmp.name)
    tmp.close()

    # Build a scale+pad filter to preserve content and fit the target aspect
    # Uses: scale=iw*min(TW/iw,TH/ih):ih*min(TW/iw,TH/ih),pad=TW:TH:(ow-iw)/2:(oh-ih)/2
    scale_expr = f"iw*min({target_w}/iw\\,{target_h}/ih):ih*min({target_w}/iw\\,{target_h}/ih)"
    pad_expr = f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2"
    vf = f"scale={scale_expr},{pad_expr}"

    cmd = [
        "ffmpeg", "-y", "-i", str(clip_path),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "copy",
        str(out_path),
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        # Cleanup temp file on failure
        out_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Failed to transcode clip: {e.stderr.decode('utf-8', errors='ignore')}")

    return FileResponse(
        path=str(out_path),
        filename=filename,
        media_type="video/mp4",
        background=BackgroundTask(out_path.unlink, missing_ok=True),
    )


@router.get("/download-all/{job_id}")
async def download_all_clips(request: Request, job_id: str):
    """Create a ZIP archive containing every generated clip for a job."""
    user = get_current_user(request)
    user_id = user["id"] if user else None

    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if user_id and job.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    if job["status"] != JobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Clips are not ready to download yet")

    job_clip_dir = (CLIP_DIR / job_id).resolve()
    clip_paths = []
    for clip in job["clips"]:
        clip_path = (job_clip_dir / clip["filename"]).resolve()
        if clip_path.parent != job_clip_dir or not clip_path.is_file():
            raise HTTPException(status_code=404, detail=f"Clip not found: {clip['filename']}")
        clip_paths.append(clip_path)

    if not clip_paths:
        raise HTTPException(status_code=404, detail="No clips available to download")

    archive = tempfile.NamedTemporaryFile(prefix=f"clipo-{job_id}-", suffix=".zip", delete=False)
    archive_path = Path(archive.name)
    archive.close()
    try:
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            for clip_path in clip_paths:
                zip_file.write(clip_path, arcname=clip_path.name)
    except Exception:
        archive_path.unlink(missing_ok=True)
        raise

    return FileResponse(
        path=str(archive_path),
        filename=f"clipo-clips-{job_id}.zip",
        media_type="application/zip",
        background=BackgroundTask(archive_path.unlink, missing_ok=True),
    )
