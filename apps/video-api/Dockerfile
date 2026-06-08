# syntax=docker/dockerfile:1.7
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIDEO_API_REPO_ROOT=/workspace \
    VIDEO_API_JOBS_ROOT=/data/jobs

# --- System layer ---------------------------------------------------------
# Rarely changes (texlive is heavy). Kept first so it stays cached across
# almost every rebuild.
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
    # Readable UI font for slides. DejaVu Sans renders "rn" as "m" at small sizes
    # ("internet" -> "intemet"); Inter avoids that and looks more professional.
    fontconfig \
    fonts-inter \
    # Manim MathTex/Tex needs a LaTeX toolchain + dvisvgm (not just latex-base).
    dvisvgm \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-latex-recommended \
    texlive-fonts-recommended \
    texlive-science \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

# uv installed once, independent of the project so it stays cached.
RUN pip install --no-cache-dir uv

WORKDIR /workspace

# --- Dependency layer -----------------------------------------------------
# Only the manifest is copied here, so this heavy layer (torch, manim,
# chatterbox-tts, ...) is rebuilt ONLY when pyproject.toml changes, not on
# every source edit. `-r pyproject.toml` installs the third-party deps but
# NOT the project itself (done later, after the source is copied).
COPY apps/video-api/pyproject.toml apps/video-api/README.md /workspace/apps/video-api/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r /workspace/apps/video-api/pyproject.toml \
    --extra worker --extra test

# --- Source layer ---------------------------------------------------------
# Editing any of these only re-runs the cheap steps below, never the deps.
COPY apps/video-api/src /workspace/apps/video-api/src
COPY apps/video-api/tests /workspace/apps/video-api/tests
# docs/ holds manim-skill.md and manim-generation-guidelines.md, read at runtime by the
# scene_coder and blueprint LLM. Without this the worker silently loses all Manim guidance.
COPY apps/video-api/docs /workspace/apps/video-api/docs
COPY docs/boilerplate /workspace/docs/boilerplate
COPY videos/linux-fondamentaux/002-c-est-quoi-un-syscall/generate_voice_en.py \
    /workspace/videos/linux-fondamentaux/002-c-est-quoi-un-syscall/generate_voice_en.py

# Editable install of the project only (deps already satisfied above). Fast.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system --no-deps -e /workspace/apps/video-api

WORKDIR /workspace/apps/video-api
