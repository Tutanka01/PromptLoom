from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from video_api import timing


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _default_repo_root() -> Path:
    # src/video_api/config.py -> src -> video-api -> apps -> repo
    return Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class Settings:
    app_name: str = "Kernel Video API"
    log_level: str = os.getenv("VIDEO_API_LOG_LEVEL", "INFO")
    database_url: str = os.getenv(
        "VIDEO_API_DATABASE_URL",
        "postgresql+psycopg://video:video@postgres:5432/video_api",
    )
    redis_url: str = os.getenv("VIDEO_API_REDIS_URL", "redis://redis:6379/0")
    jobs_root: Path = Path(os.getenv("VIDEO_API_JOBS_ROOT", "apps/video-api/data/jobs"))
    repo_root: Path = Path(os.getenv("VIDEO_API_REPO_ROOT", str(_default_repo_root())))
    max_repair_attempts: int = int(os.getenv("VIDEO_API_MAX_REPAIR_ATTEMPTS", "2"))
    fake_llm: bool = _bool_env("VIDEO_API_FAKE_LLM", False)
    default_target_duration_seconds: int = int(
        os.getenv("VIDEO_API_DEFAULT_TARGET_DURATION_SECONDS", str(timing.DEFAULT_TARGET_DURATION_SECONDS))
    )
    default_min_duration_seconds: int = int(
        os.getenv("VIDEO_API_DEFAULT_MIN_DURATION_SECONDS", str(timing.DEFAULT_MIN_DURATION_SECONDS))
    )

    openai_base_url: str | None = os.getenv("OPENAI_BASE_URL")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4.1")
    llm_temperature: float = float(os.getenv("VIDEO_API_LLM_TEMPERATURE", "0.35"))
    llm_timeout_seconds: float = float(os.getenv("VIDEO_API_LLM_TIMEOUT_SECONDS", "180"))
    llm_response_format: str = os.getenv("VIDEO_API_LLM_RESPONSE_FORMAT", "json_object")
    llm_max_tokens: int = int(os.getenv("VIDEO_API_LLM_MAX_TOKENS", "8000"))
    # Reasoning ("thinking") models (e.g. Qwen3) burn the whole token/time budget on
    # hidden reasoning and return empty/truncated JSON. Keep this OFF for structured
    # blueprint generation unless the endpoint genuinely needs it.
    llm_enable_thinking: bool = _bool_env("VIDEO_API_LLM_ENABLE_THINKING", False)
    # The OpenAI SDK retries timeouts twice by default, turning one slow call into a
    # 3x hang. Keep retries low so a stuck request fails fast and surfaces clearly.
    llm_max_retries: int = int(os.getenv("VIDEO_API_LLM_MAX_RETRIES", "1"))

    # v1 default: the LLM only produces a JSON blueprint and the worker renders it from
    # tested deterministic templates. Free-form per-scene Python (scene_coder) is fragile
    # with open-source models, so it is opt-in.
    scene_coder_enabled: bool = _bool_env("VIDEO_API_SCENE_CODER_ENABLED", False)
    scene_coder_model: str = os.getenv("VIDEO_API_SCENE_CODER_MODEL", "")
    scene_coder_attempts: int = int(os.getenv("VIDEO_API_SCENE_CODER_ATTEMPTS", "3"))

    visual_review_enabled: bool = _bool_env("VIDEO_API_VISION_ENABLED", False)
    visual_review_model: str = os.getenv("VIDEO_API_VISION_MODEL", "")
    visual_review_min_score: float = float(os.getenv("VIDEO_API_VISION_MIN_SCORE", "75"))
    visual_review_max_tokens: int = int(os.getenv("VIDEO_API_VISION_MAX_TOKENS", "1500"))

    voice_command: str = os.getenv(
        "VIDEO_API_VOICE_COMMAND",
        "uv run --python 3.11 --with chatterbox-tts python generate_voice_en.py "
        "--engine chatterbox --exaggeration 0.45 --cfg-weight 0.55 "
        "--temperature 0.55 --tail-padding 0.45",
    )
    command_timeout_seconds: int = int(os.getenv("VIDEO_API_COMMAND_TIMEOUT_SECONDS", "14400"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
