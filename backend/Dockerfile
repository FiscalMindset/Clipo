FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# ffmpeg is required by the app (fatal exit if missing); curl+unzip+git are
# needed to fetch the deno/node binaries and the PO-token provider below.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    unzip \
    git \
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

# Node.js >= 20 powers the bgutil PO-token provider server (see below).
# Installed as a pinned binary tarball (like deno) so we do not depend on the
# distro's old Node.
ARG NODE_VERSION=v22.14.0
RUN set -eux; \
    case "$(uname -m)" in \
      aarch64|arm64) NARCH=linux-arm64 ;; \
      *) NARCH=linux-x64 ;; \
    esac; \
    curl -fsSL -o /tmp/node.tar.gz "https://nodejs.org/dist/${NODE_VERSION}/node-${NODE_VERSION}-${NARCH}.tar.gz" \
    && tar -xzf /tmp/node.tar.gz -C /usr/local --strip-components=1 \
    && rm /tmp/node.tar.gz \
    && node --version && npm --version

# The bgutil PO-token provider: a local HTTP server (default port 4416) that
# mints proof-of-origin tokens. yt-dlp attaches one to the ``web`` player to
# get past the "Sign in to confirm you're not a bot" wall that YouTube shows
# on flagged datacenter IPs (Azure). The yt-dlp plugin side ships from pip
# (requirements.txt); this is the token-minting server. Pinned to the 1.3.1
# release and built exactly like the project's own Dockerfile (npm ci + tsc,
# then dev dependencies are pruned away).
RUN set -eux; \
    git clone --depth 1 --branch 1.3.1 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /opt/bgutil-provider \
    && cd /opt/bgutil-provider/server \
    && npm ci --no-audit --no-fund \
    && npx tsc \
    && npm prune --omit=dev

WORKDIR /app/backend

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Data dirs live at the project root (above WORKDIR); created on import by config.py
ENV WHISPER_DEVICE=cpu \
    WHISPER_COMPUTE_TYPE=int8

EXPOSE 8000

CMD ["sh", "-c", "node /opt/bgutil-provider/server/build/main.js --port 4416 & exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
