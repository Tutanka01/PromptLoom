# syntax=docker/dockerfile:1.7
# Linux torch wheels bundle the CUDA runtime: the host only needs the NVIDIA
# driver + nvidia-container-toolkit (compose reserves the GPU), no CUDA base
# image required.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/data/hf-cache \
    TTS_SERVER_DATA_DIR=/data

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    ffmpeg \
    # gcc: recent torch dispatches some *eager* ops to Triton kernels, and
    # Triton builds its CUDA utils module at runtime — without a C compiler
    # generation dies with "RuntimeError: Failed to find C compiler".
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

# --- Dependency layer ------------------------------------------------------
# Only the manifest is copied here so the heavy layer (torch CUDA,
# transformers) is rebuilt ONLY when pyproject.toml changes.
COPY pyproject.toml README.md /app/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r /app/pyproject.toml --extra gpu --extra test

# --- Source layer ----------------------------------------------------------
COPY src /app/src
COPY tests /app/tests
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system --no-deps -e /app

EXPOSE 8100
# --factory: the app builds (and touches /data) at startup, not at import.
CMD ["uvicorn", "tts_server.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8100"]
