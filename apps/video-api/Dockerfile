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
    # espeak-ng: grapheme->phoneme backend for Kokoro TTS (required for French,
    # used by misaki[fr]). Harmless when the Chatterbox engine is used.
    espeak-ng \
    ffmpeg \
    git \
    libcairo2-dev \
    libpango1.0-dev \
    pkg-config \
    python3-dev \
    # Readable UI font for slides. DejaVu Sans renders "rn" as "m" at small sizes
    # ("internet" -> "intemet"); Inter avoids that and looks more professional.
    # JetBrains Mono is the code/mono face the Remotion tokens ask for; without it
    # CodeScene/TerminalScene fall back to DejaVu Sans Mono. Both faces are named
    # in remotion/src/style/tokens.ts (fonts.sans / fonts.mono) and render in the
    # headless Chrome with no render-time network fetch.
    fontconfig \
    fonts-inter \
    fonts-jetbrains-mono \
    # Manim MathTex/Tex needs a LaTeX toolchain + dvisvgm (not just latex-base).
    dvisvgm \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-latex-recommended \
    texlive-fonts-recommended \
    texlive-science \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

# --- Node + headless Chrome layer -----------------------------------------
# For the Remotion render engine (VIDEO_API_RENDER_ENGINE=remotion). Stable, so
# kept high for caching. The libs are what Remotion's headless Chrome needs.
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get install -y --no-install-recommends \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxext6 libxfixes3 libxrandr2 libgbm1 \
    libasound2 libpango-1.0-0 libpangocairo-1.0-0 libxshmfence1 \
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
# Pre-download the MMS_FA forced-alignment weights (~300 MB) into the torch hub
# cache so the audio_alignment step never downloads at job time. Failure is
# tolerated (offline build): the worker would then fetch lazily on first use.
RUN python -c "from torchaudio.pipelines import MMS_FA; MMS_FA.get_model(with_star=False)" || \
    echo "WARNING: MMS_FA pre-download failed; weights will download on first use"

# --- Remotion dependency layer --------------------------------------------
# Only the manifest is copied here so `npm ci` + the Chrome Headless Shell
# download are cached unless the lockfile changes (not on every src edit).
COPY apps/video-api/remotion/package.json apps/video-api/remotion/package-lock.json \
    /workspace/apps/video-api/remotion/
RUN cd /workspace/apps/video-api/remotion && npm ci
# Pre-download Chrome Headless Shell so runtime renders never fetch it.
RUN cd /workspace/apps/video-api/remotion && npx --no-install remotion browser ensure

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
# Remotion engine sources (catalog + data scenes + generated-entry targets).
COPY apps/video-api/remotion/tsconfig.json apps/video-api/remotion/remotion.config.ts \
    /workspace/apps/video-api/remotion/
COPY apps/video-api/remotion/src /workspace/apps/video-api/remotion/src

# Editable install of the project only (deps already satisfied above). Fast.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system --no-deps -e /workspace/apps/video-api

WORKDIR /workspace/apps/video-api
