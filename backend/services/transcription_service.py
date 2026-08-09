"""
Transcription Service — uses local Whisper when available, otherwise falls back
to Gemini audio transcription so uploads still work on restricted Windows machines.
"""

import asyncio
import functools
import json
import wave
from pathlib import Path
from typing import Any

import aiofiles
from google import genai
from google.genai import types

from config import (
    DEEPGRAM_API_KEY,
    DEEPGRAM_MODEL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    TRANSCRIPTION_PROVIDER,
    TRANSCRIPT_DIR,
    WHISPER_COMPUTE_TYPE,
    WHISPER_DEVICE,
    WHISPER_MODEL,
)
from models.schemas import TranscriptResponse
from services.gemini_keys import next_key, mark_rate_limited, is_rate_limited_error


def _transcribe_sync(audio_path: str, model: Any) -> dict:
    """
    Run Whisper transcription synchronously.
    This is called via run_in_executor to avoid blocking the event loop.
    """
    segments_raw, info = model.transcribe(
        audio_path,
        word_timestamps=True,
        vad_filter=True,       # Filter out silence for better timestamps
        vad_parameters=dict(
            min_silence_duration_ms=500,
        ),
    )

    segments = []
    full_text_parts = []

    for segment in segments_raw:
        seg_data = {
            "start": round(segment.start, 2),
            "end": round(segment.end, 2),
            "text": segment.text.strip(),
        }

        # Include word-level timestamps if available
        if segment.words:
            seg_data["words"] = [
                {
                    "word": w.word.strip(),
                    "start": round(w.start, 2),
                    "end": round(w.end, 2),
                }
                for w in segment.words
            ]

        segments.append(seg_data)
        full_text_parts.append(segment.text.strip())

    return {
        "text": " ".join(full_text_parts),
        "segments": segments,
        "language": info.language,
        "duration": info.duration,
    }


def _audio_duration_seconds(audio_path: Path) -> float:
    with wave.open(str(audio_path), "rb") as wav_file:
        frame_count = wav_file.getnframes()
        frame_rate = wav_file.getframerate() or 1
        return frame_count / float(frame_rate)


async def _transcribe_with_deepgram(audio_path: Path) -> dict:
    """Transcribe a WAV with Deepgram and preserve word timestamps for captions."""
    if not DEEPGRAM_API_KEY:
        raise RuntimeError(
            "DEEPGRAM_API_KEY is not set. Add it to .env, or set TRANSCRIPTION_PROVIDER=whisper "
            "to use the retained local Whisper transcription path."
        )

    import httpx

    params = {
        "model": DEEPGRAM_MODEL,
        "smart_format": "true",
        "punctuate": "true",
        "utterances": "true",
    }
    headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}", "Content-Type": "audio/wav"}

    async def audio_stream():
        """Yield the audio asynchronously so httpx never receives a sync file handle."""
        async with aiofiles.open(audio_path, "rb") as audio_file:
            while chunk := await audio_file.read(1024 * 1024):
                yield chunk

    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=30.0)) as client:
        response = await client.post(
            "https://api.deepgram.com/v1/listen",
            params=params,
            headers=headers,
            content=audio_stream(),
        )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500]
        raise RuntimeError(f"Deepgram transcription failed ({exc.response.status_code}): {detail}") from exc

    payload = response.json()
    result = payload.get("results", {})
    channel = (result.get("channels") or [{}])[0]
    alternative = (channel.get("alternatives") or [{}])[0]
    words = alternative.get("words") or []
    utterances = result.get("utterances") or []
    duration = float((payload.get("metadata") or {}).get("duration") or _audio_duration_seconds(audio_path))

    segments = []
    for utterance in utterances:
        segment_words = [
            {"word": word["word"], "start": round(word["start"], 2), "end": round(word["end"], 2)}
            for word in words
            if word.get("start", 0) >= utterance.get("start", 0)
            and word.get("end", 0) <= utterance.get("end", duration)
        ]
        segments.append({
            "start": round(utterance.get("start", 0), 2),
            "end": round(utterance.get("end", 0), 2),
            "text": utterance.get("transcript", "").strip(),
            "words": segment_words,
        })
    if not segments and words:
        segments = [{
            "start": round(words[0]["start"], 2),
            "end": round(words[-1]["end"], 2),
            "text": alternative.get("transcript", "").strip(),
            "words": [{"word": w["word"], "start": round(w["start"], 2), "end": round(w["end"], 2)} for w in words],
        }]

    return {
        "text": alternative.get("transcript", "").strip(),
        "segments": segments,
        "language": (result.get("channels") or [{}])[0].get("detected_language", "en"),
        "duration": duration,
    }


def load_local_whisper_model() -> Any | None:
    """Load faster-whisper if it is usable on this machine."""
    import os
    if os.environ.get("RENDER"):
        print("Running on Render free tier (512MB RAM) - Disabling local Whisper model to prevent Out Of Memory crash!")
        return None

    try:
        from faster_whisper import WhisperModel
    except Exception as exc:
        print(f"Local Whisper unavailable; falling back to Gemini transcription: {exc}")
        return None

    attempts: list[tuple[str, str]] = [(WHISPER_DEVICE, WHISPER_COMPUTE_TYPE)]
    if WHISPER_DEVICE == "cuda":
        attempts.append(("cpu", "int8"))

    last_error: Exception | None = None
    for device, compute_type in attempts:
        try:
            print(f"Loading Whisper model '{WHISPER_MODEL}' on {device} ({compute_type})...")
            return WhisperModel(
                WHISPER_MODEL,
                device=device,
                compute_type=compute_type,
            )
        except Exception as exc:
            last_error = exc
            print(f"Whisper load failed on {device} ({compute_type}): {exc}")

    if last_error is not None:
        print(f"Local Whisper unavailable; falling back to Gemini transcription: {last_error}")
    return None


def _transcribe_with_gemini_sync(audio_path: Path, job_id: str, api_key: str) -> dict:
    if not api_key:
        raise RuntimeError(
            "Local Whisper is unavailable on this machine and GEMINI_API_KEY is not set."
        )

    client = genai.Client(api_key=api_key)
    duration = _audio_duration_seconds(audio_path)

    uploaded = client.files.upload(file=audio_path, config={"mime_type": "audio/wav"})
    audio_part = types.Part.from_uri(
        file_uri=uploaded.uri,
        mime_type=uploaded.mime_type or "audio/wav",
    )

    prompt = f"""Transcribe this audio into JSON.

Requirements:
- Return the full transcript in `text`.
- Return timestamped `segments` with `start`, `end`, and `text`.
- Use seconds with two decimal places.
- Keep the segment timestamps in chronological order and do not overlap them.
- The audio duration is approximately {duration:.2f} seconds.
"""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[prompt, audio_part],
            config=types.GenerateContentConfig(
                system_instruction="You are a precise transcription engine. Return only valid JSON.",
                response_mime_type="application/json",
                response_schema=TranscriptResponse,
                temperature=0.0,
            ),
        )
        parsed = response.parsed
        if not parsed:
            raise RuntimeError("Gemini transcription returned no result.")

        segments = [
            {
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "text": segment.text.strip(),
            }
            for segment in parsed.segments
        ]
        if not segments:
            segments = [
                {
                    "start": 0.0,
                    "end": round(duration, 2),
                    "text": parsed.text.strip(),
                }
            ]

        return {
            "text": parsed.text.strip(),
            "segments": segments,
            "language": parsed.language or "en",
            "duration": duration,
        }
    finally:
        try:
            if getattr(uploaded, "name", None):
                client.files.delete(name=uploaded.name)
        except Exception:
            pass


async def transcribe(audio_path: Path, model: Any | None, job_id: str) -> dict:
    """
    Transcribe audio file using local faster-whisper when available, otherwise
    use Gemini as a fallback so processing still works on machines that cannot
    load the local Whisper backend.
    """
    loop = asyncio.get_running_loop()

    if TRANSCRIPTION_PROVIDER == "deepgram":
        result = await _transcribe_with_deepgram(audio_path)
    elif model is not None:
        # Run the CPU/GPU-heavy transcription in a thread.
        result = await loop.run_in_executor(
            None,
            functools.partial(_transcribe_sync, str(audio_path), model),
        )
    else:
        # Gemini fallback. Upload + generate must use the same key, so rotate at
        # the whole-operation level: on rate limit, mark the key and retry with a
        # different one.
        last_error: Exception | None = None
        for _ in range(4):
            api_key = next_key() or GEMINI_API_KEY
            try:
                result = await loop.run_in_executor(
                    None,
                    functools.partial(_transcribe_with_gemini_sync, audio_path, job_id, api_key),
                )
                break
            except Exception as error:
                last_error = error
                if is_rate_limited_error(error):
                    mark_rate_limited(api_key)
                    continue
                raise
        else:
            raise last_error

    # Save transcript to disk
    transcript_path = TRANSCRIPT_DIR / f"{job_id}_transcript.json"
    with open(transcript_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    return result
