FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# ffmpeg is required by the app (fatal exit if missing); curl+unzip are
# needed to fetch the deno binary below.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# deno is used by yt-dlp to solve YouTube's JS challenges (signature + n
# parameter). Without a JS runtime those formats cannot be resolved and
# downloads fail with "Requested format is not available".
#
# The binary must match the image architecture — hardcoding x86_64 breaks
# arm64 builds with a SIGTRAP crash. Version is pinned to a known-good
# release for the python:3.12-slim base.
ARG DENO_VERSION=v1.46.3
RUN set -eux; \
    case "$(uname -m)" in \
      aarch64|arm64) DARCH=aarch64-unknown-linux-gnu ;; \
      *) DARCH=x86_64-unknown-linux-gnu ;; \
    esac; \
    curl -fsSL -o /tmp/deno.zip "https://github.com/denoland/deno/releases/download/${DENO_VERSION}/deno-${DARCH}.zip" \
    && unzip -o /tmp/deno.zip -d /usr/local/bin \
    && rm /tmp/deno.zip \
    && chmod +x /usr/local/bin/deno \
    && deno --version

WORKDIR /app/backend

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Data dirs live at the project root (above WORKDIR); created on import by config.py
ENV WHISPER_DEVICE=cpu \
    WHISPER_COMPUTE_TYPE=int8

EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
