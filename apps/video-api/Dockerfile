FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIDEO_API_REPO_ROOT=/workspace \
    VIDEO_API_JOBS_ROOT=/data/jobs

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    curl \
    ffmpeg \
    git \
    libcairo2-dev \
    libpango1.0-dev \
    pkg-config \
    python3-dev \
    texlive-latex-base \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY apps/video-api/pyproject.toml apps/video-api/README.md /workspace/apps/video-api/
COPY apps/video-api/src /workspace/apps/video-api/src
COPY apps/video-api/tests /workspace/apps/video-api/tests
COPY docs/boilerplate /workspace/docs/boilerplate
COPY videos/linux-fondamentaux/002-c-est-quoi-un-syscall/generate_voice_en.py \
    /workspace/videos/linux-fondamentaux/002-c-est-quoi-un-syscall/generate_voice_en.py

RUN pip install --no-cache-dir uv \
    && uv pip install --system -e /workspace/apps/video-api[worker,test]

WORKDIR /workspace/apps/video-api
