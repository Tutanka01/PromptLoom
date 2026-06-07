from __future__ import annotations

import os
from dataclasses import dataclass, field
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


def _env_path() -> Path:
    override = os.getenv("VIDEO_API_ENV_FILE")
    if override:
        return Path(override)
    return _default_repo_root() / "apps" / "video-api" / ".env"


def _unquote_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    if " #" in value:
        value = value.split(" #", 1)[0].rstrip()
    return value


def _load_dotenv_if_present() -> None:
    """Load apps/video-api/.env for local runs without overriding process env."""
    path = _env_path()
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key.startswith("#") or key in os.environ:
            continue
        os.environ[key] = _unquote_env_value(value)


_load_dotenv_if_present()


@dataclass(frozen=True)
class Settings:
    app_name: str = "Kernel Video API"
    log_level: str = field(default_factory=lambda: os.getenv("VIDEO_API_LOG_LEVEL", "INFO"))
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "VIDEO_API_DATABASE_URL",
            "postgresql+psycopg://video:video@postgres:5432/video_api",
        )
    )
    redis_url: str = field(default_factory=lambda: os.getenv("VIDEO_API_REDIS_URL", "redis://redis:6379/0"))
    jobs_root: Path = field(
        default_factory=lambda: Path(os.getenv("VIDEO_API_JOBS_ROOT", "apps/video-api/data/jobs"))
    )
    repo_root: Path = field(default_factory=lambda: Path(os.getenv("VIDEO_API_REPO_ROOT", str(_default_repo_root()))))
    max_repair_attempts: int = field(
        default_factory=lambda: int(os.getenv("VIDEO_API_MAX_REPAIR_ATTEMPTS", "2"))
    )
    fake_llm: bool = field(default_factory=lambda: _bool_env("VIDEO_API_FAKE_LLM", False))
    default_target_duration_seconds: int = field(
        default_factory=lambda: int(
            os.getenv("VIDEO_API_DEFAULT_TARGET_DURATION_SECONDS", str(timing.DEFAULT_TARGET_DURATION_SECONDS))
        )
    )
    default_min_duration_seconds: int = field(
        default_factory=lambda: int(
            os.getenv("VIDEO_API_DEFAULT_MIN_DURATION_SECONDS", str(timing.DEFAULT_MIN_DURATION_SECONDS))
        )
    )

    openai_base_url: str | None = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL"))
    openai_api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4.1"))
    llm_temperature: float = field(default_factory=lambda: float(os.getenv("VIDEO_API_LLM_TEMPERATURE", "0.35")))
    llm_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("VIDEO_API_LLM_TIMEOUT_SECONDS", "180"))
    )
    llm_response_format: str = field(
        default_factory=lambda: os.getenv("VIDEO_API_LLM_RESPONSE_FORMAT", "json_object")
    )
    llm_max_tokens: int = field(default_factory=lambda: int(os.getenv("VIDEO_API_LLM_MAX_TOKENS", "8000")))
    # Reasoning ("thinking") models (e.g. Qwen3) burn the whole token/time budget on
    # hidden reasoning and return empty/truncated JSON. Keep this OFF for structured
    # blueprint generation unless the endpoint genuinely needs it.
    llm_enable_thinking: bool = field(default_factory=lambda: _bool_env("VIDEO_API_LLM_ENABLE_THINKING", False))
    # The OpenAI SDK retries timeouts twice by default, turning one slow call into a
    # 3x hang. Keep retries low so a stuck request fails fast and surfaces clearly.
    llm_max_retries: int = field(default_factory=lambda: int(os.getenv("VIDEO_API_LLM_MAX_RETRIES", "1")))

    # v2 default: the LLM authors real, free-form Manim per scene (scene_coder) so videos
    # are visually varied and can use LaTeX, plotted axes and code blocks instead of one
    # fixed card grammar. The deterministic template stays as a per-scene fallback when a
    # generated scene fails validation or compilation. Set =0 to force deterministic-only.
    scene_coder_enabled: bool = field(default_factory=lambda: _bool_env("VIDEO_API_SCENE_CODER_ENABLED", True))
    scene_coder_model: str = field(default_factory=lambda: os.getenv("VIDEO_API_SCENE_CODER_MODEL", ""))
    scene_coder_attempts: int = field(
        default_factory=lambda: int(os.getenv("VIDEO_API_SCENE_CODER_ATTEMPTS", "3"))
    )
    scene_coder_max_tokens: int = field(
        default_factory=lambda: int(os.getenv("VIDEO_API_SCENE_CODER_MAX_TOKENS", "4096"))
    )

    visual_review_enabled: bool = field(default_factory=lambda: _bool_env("VIDEO_API_VISION_ENABLED", False))
    visual_review_model: str = field(default_factory=lambda: os.getenv("VIDEO_API_VISION_MODEL", ""))
    visual_review_min_score: float = field(
        default_factory=lambda: float(os.getenv("VIDEO_API_VISION_MIN_SCORE", "75"))
    )
    visual_review_max_tokens: int = field(
        default_factory=lambda: int(os.getenv("VIDEO_API_VISION_MAX_TOKENS", "1500"))
    )

    voice_engine: str = field(default_factory=lambda: os.getenv("VIDEO_API_VOICE_ENGINE", "chatterbox"))
    voice_command: str = field(
        default_factory=lambda: os.getenv(
            "VIDEO_API_VOICE_COMMAND",
            "uv run --python 3.11 --with chatterbox-tts python generate_voice_en.py "
            "--engine chatterbox --exaggeration 0.45 --cfg-weight 0.55 "
            "--temperature 0.55 --tail-padding 0.45",
        )
    )
    voice_tail_padding: float = field(default_factory=lambda: float(os.getenv("VIDEO_API_VOICE_TAIL_PADDING", "0.45")))
    openai_tts_model: str = field(
        default_factory=lambda: os.getenv("VIDEO_API_OPENAI_TTS_MODEL") or os.getenv("OPENAI_TTS_MODEL", "tts-1")
    )
    openai_tts_voice: str = field(
        default_factory=lambda: os.getenv("VIDEO_API_OPENAI_TTS_VOICE") or os.getenv("OPENAI_TTS_VOICE", "alloy")
    )
    openai_tts_format: str = field(default_factory=lambda: os.getenv("VIDEO_API_OPENAI_TTS_FORMAT", "wav"))
    openai_tts_speed: float = field(default_factory=lambda: float(os.getenv("VIDEO_API_OPENAI_TTS_SPEED", "1.0")))
    command_timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("VIDEO_API_COMMAND_TIMEOUT_SECONDS", "14400"))
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
