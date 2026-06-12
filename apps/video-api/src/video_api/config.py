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
    # Rendering engine. "manim" (default) keeps the existing Python/Manim path.
    # "remotion" switches materialize + render to the React/Remotion engine
    # (data-driven component palette), reusing the same TTS, assemble and verify
    # steps. This is the only switch needed to change engines.
    render_engine: str = field(default_factory=lambda: os.getenv("VIDEO_API_RENDER_ENGINE", "manim").strip().lower())
    # Render speed knobs (no-GPU VM: the Remotion render is CPU-bound on software GL,
    # so concurrency + frame count + x264 preset are the real levers).
    # - render_fps: output frame rate. 30 (default) halves the frames to encode vs 60
    #   for explainer content; raise to 60 for maximum smoothness.
    # - remotion_concurrency: passed to `remotion render --concurrency`. Accepts an int
    #   or a percentage ("75%" ~= 12 tabs on 16 cores). Each Chrome tab uses ~0.5-1 GB,
    #   so on 16 GB cap near ~10-12; lower to "50%" if the worker OOMs.
    # - render_x264_preset: x264 preset for the final encode. "faster" trades a little
    #   file size for a big speed win at crf 18 with near-invisible quality loss.
    render_fps: int = field(default_factory=lambda: int(os.getenv("VIDEO_API_RENDER_FPS", "30")))
    remotion_concurrency: str = field(
        default_factory=lambda: os.getenv("VIDEO_API_REMOTION_CONCURRENCY", "75%")
    )
    render_x264_preset: str = field(
        default_factory=lambda: os.getenv("VIDEO_API_RENDER_X264_PRESET", "faster")
    )
    # Word-level forced alignment of the TTS audio (Remotion engine only). Drives
    # narration-synced visual cues (props.cues): each item reveals when its words
    # are actually spoken instead of on an even grid. torchaudio MMS_FA; CPU is
    # fine for short English segments, "auto" picks CUDA when available. Failures
    # are non-fatal (scenes keep their default timings).
    align_enabled: bool = field(default_factory=lambda: _bool_env("VIDEO_API_ALIGN_ENABLED", True))
    align_device: str = field(default_factory=lambda: os.getenv("VIDEO_API_ALIGN_DEVICE", "auto"))
    # Optional background music under the voiceover. Point VIDEO_API_MUSIC_FILE
    # at an audio file readable from the worker (e.g. a CC0 ambient loop under
    # /data); it is looped, attenuated by VIDEO_API_MUSIC_DB (default -26 dB)
    # and sidechain-ducked by the voice in assemble_en.sh. Empty = no music
    # (no asset ships with the repo).
    music_file: str = field(default_factory=lambda: os.getenv("VIDEO_API_MUSIC_FILE", ""))
    music_gain_db: float = field(default_factory=lambda: float(os.getenv("VIDEO_API_MUSIC_DB", "-26")))
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
    # Freeze gate (final render). Held formulas in math videos read as "frozen", so the
    # gate uses two signals: cumulative frozen time (tolerant — a video may legitimately
    # hold visuals) and the single longest frozen stretch (strict — catches a dead scene).
    # The video fails if EITHER the total exceeds max(floor, duration*ratio) or any single
    # stretch exceeds the single-freeze cap.
    verify_max_freeze_ratio: float = field(
        default_factory=lambda: float(os.getenv("VIDEO_API_MAX_FREEZE_RATIO", "0.5"))
    )
    verify_freeze_floor_seconds: float = field(
        default_factory=lambda: float(os.getenv("VIDEO_API_FREEZE_FLOOR_SECONDS", "30"))
    )
    verify_max_single_freeze_seconds: float = field(
        default_factory=lambda: float(os.getenv("VIDEO_API_MAX_FREEZE_SINGLE_SECONDS", "12"))
    )
    # Freeze fatality. On the Remotion engine a long freeze is a real bug (the
    # AmbientBackground guarantees continuous motion, so a frozen stretch means a
    # scene crashed or rendered nothing) — fatal by default. On Manim, held
    # formulas legitimately read as "frozen" — warning by default. Override with
    # VIDEO_API_FREEZE_FATAL=0/1.
    verify_freeze_fatal: bool = field(
        default_factory=lambda: _bool_env(
            "VIDEO_API_FREEZE_FATAL",
            os.getenv("VIDEO_API_RENDER_ENGINE", "manim").strip().lower() == "remotion",
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
    # Concurrent LLM calls for per-scene work (scene coders, per-scene blueprint
    # passes). Scenes are independent and the calls are I/O-bound, so a small pool
    # cuts wall time by ~N. Keep modest: a local vLLM/llama.cpp endpoint saturates
    # quickly and slows every request when over-subscribed.
    llm_parallel: int = field(default_factory=lambda: max(1, int(os.getenv("VIDEO_API_LLM_PARALLEL", "3"))))
    # Two-pass Remotion blueprint generation: pass 1 plans a compact outline
    # (structure, components, pedagogy), pass 2 writes each scene in parallel
    # (narration + props + beat anchors) with strict per-scene validation and
    # targeted retries. The model focuses on ~60 words and one component at a
    # time instead of a whole 8-12 scene video, which is where narration and
    # prop quality is won. Set =0 to fall back to the legacy single-pass call.
    blueprint_two_pass: bool = field(default_factory=lambda: _bool_env("VIDEO_API_BLUEPRINT_TWO_PASS", True))
    # Targeted retries when one scene of pass 2 fails validation (placeholder
    # props, anchors not found in the narration, item/beat count mismatch).
    blueprint_scene_attempts: int = field(
        default_factory=lambda: max(1, int(os.getenv("VIDEO_API_BLUEPRINT_SCENE_ATTEMPTS", "2")))
    )

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
    # Prove each generated scene actually renders (undefined-name check + single-scene
    # smoke render) before trusting it, so a runtime error in one scene triggers repair /
    # fallback instead of killing the whole job at the global render. Set =0 to disable.
    scene_coder_smoke_render: bool = field(
        default_factory=lambda: _bool_env("VIDEO_API_SCENE_CODER_SMOKE_RENDER", True)
    )
    scene_coder_smoke_timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("VIDEO_API_SCENE_CODER_SMOKE_TIMEOUT", "150"))
    )

    # Visual review auto-enables when a vision model is configured: setting
    # VIDEO_API_VISION_MODEL is an unambiguous "I want review", so requiring a
    # second flag just left the gate silently off. VIDEO_API_VISION_ENABLED
    # still overrides in both directions.
    visual_review_enabled: bool = field(
        default_factory=lambda: _bool_env(
            "VIDEO_API_VISION_ENABLED", bool(os.getenv("VIDEO_API_VISION_MODEL", "").strip())
        )
    )
    visual_review_model: str = field(default_factory=lambda: os.getenv("VIDEO_API_VISION_MODEL", ""))
    visual_review_min_score: float = field(
        default_factory=lambda: float(os.getenv("VIDEO_API_VISION_MIN_SCORE", "75"))
    )
    visual_review_max_tokens: int = field(
        default_factory=lambda: int(os.getenv("VIDEO_API_VISION_MAX_TOKENS", "1500"))
    )

    voice_engine: str = field(default_factory=lambda: os.getenv("VIDEO_API_VOICE_ENGINE", "chatterbox"))
    # Language for the local TTS (currently only consumed by the kokoro engine, which
    # maps en->lang_code "a", fr->lang_code "f"). Chatterbox ignores it (English model).
    voice_language: str = field(default_factory=lambda: os.getenv("VIDEO_API_VOICE_LANGUAGE", "en"))
    # Kokoro voice id (e.g. "af_bella" for EN, "ff_siwis" for FR). Used when
    # VIDEO_API_VOICE_ENGINE=kokoro. Kokoro is ~5x real-time on CPU vs Chatterbox.
    kokoro_voice: str = field(default_factory=lambda: os.getenv("VIDEO_API_KOKORO_VOICE", "af_bella"))
    voice_command: str = field(
        default_factory=lambda: os.getenv(
            "VIDEO_API_VOICE_COMMAND",
            "uv run --python 3.11 --with chatterbox-tts python generate_voice_en.py "
            "--engine chatterbox --exaggeration 0.45 --cfg-weight 0.55 "
            "--temperature 0.55 --tail-padding 0.45",
        )
    )
    voice_tail_padding: float = field(default_factory=lambda: float(os.getenv("VIDEO_API_VOICE_TAIL_PADDING", "0.45")))
    moss_tts_model: str = field(
        default_factory=lambda: os.getenv("VIDEO_API_MOSS_TTS_MODEL", "OpenMOSS-Team/MOSS-TTS-v1.5")
    )
    moss_tts_voice: str = field(default_factory=lambda: os.getenv("VIDEO_API_MOSS_TTS_VOICE", ""))
    moss_tts_reference_audio: str = field(default_factory=lambda: os.getenv("VIDEO_API_MOSS_TTS_REFERENCE_AUDIO", ""))
    moss_tts_reference_text: str = field(default_factory=lambda: os.getenv("VIDEO_API_MOSS_TTS_REFERENCE_TEXT", ""))
    moss_tts_consistent_voice: bool = field(
        default_factory=lambda: _bool_env("VIDEO_API_MOSS_TTS_CONSISTENT_VOICE", True)
    )
    moss_tts_device: str = field(default_factory=lambda: os.getenv("VIDEO_API_MOSS_TTS_DEVICE", "auto"))
    moss_tts_dtype: str = field(default_factory=lambda: os.getenv("VIDEO_API_MOSS_TTS_DTYPE", "auto"))
    moss_tts_command: str = field(default_factory=lambda: os.getenv("VIDEO_API_MOSS_TTS_COMMAND", ""))
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
    # Hard ceiling for one whole job (Celery soft/hard time limits). A job that
    # exceeds it raises SoftTimeLimitExceeded inside the pipeline (clean failure
    # in DB) and is killed 5 minutes later if it ignores that. Chatterbox on CPU
    # is slow, so the default stays generous; lower it on faster setups.
    task_time_limit_seconds: int = field(
        default_factory=lambda: int(os.getenv("VIDEO_API_TASK_TIME_LIMIT_SECONDS", "10800"))
    )
    # A job whose DB row stopped moving for this long (worker killed mid-job,
    # OOM, host reboot) is marked failed by the API at startup so it never sits
    # in "running" forever.
    stale_job_hours: float = field(
        default_factory=lambda: float(os.getenv("VIDEO_API_STALE_JOB_HOURS", "6"))
    )
    # Comma-separated API keys. Empty (default) = authentication disabled, so
    # existing deployments keep working; set it to require X-API-Key on /v1/*.
    api_keys: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            key.strip() for key in os.getenv("VIDEO_API_KEYS", "").split(",") if key.strip()
        )
    )
    # HMAC-SHA256 secret for webhook payloads (X-Video-API-Signature header).
    # Empty = webhooks are sent unsigned.
    webhook_secret: str = field(default_factory=lambda: os.getenv("VIDEO_API_WEBHOOK_SECRET", ""))
    # Workspace garbage collection: terminal jobs older than this many days get
    # their /data/jobs/<id> directory removed at API startup. 0 (default) = off.
    job_ttl_days: float = field(default_factory=lambda: float(os.getenv("VIDEO_API_JOB_TTL_DAYS", "0")))


@lru_cache
def get_settings() -> Settings:
    return Settings()


def apply_quality_profile(settings: Settings, profile: str) -> Settings:
    """Per-job overrides for the requested quality profile.

    - draft: fast iteration — Kokoro voice (~5x real-time on CPU), half-res
      render (QUALITY=ql), no visual review, fastest x264 preset, lenient final
      verify (no 1080p/fps assertion). For testing a prompt, not for shipping.
    - standard (alias: final): the configured defaults.
    - high: standard + visual review forced on (requires VIDEO_API_VISION_MODEL;
      without a model it stays off) + fatal freeze gate.
    """
    import dataclasses

    profile = (profile or "standard").strip().lower()
    if profile == "draft":
        return dataclasses.replace(
            settings,
            voice_engine="kokoro",
            visual_review_enabled=False,
            render_x264_preset="ultrafast",
        )
    if profile == "high":
        return dataclasses.replace(
            settings,
            visual_review_enabled=bool(settings.visual_review_model),
            verify_freeze_fatal=True,
        )
    return settings


def render_quality_for_profile(profile: str) -> str:
    """QUALITY env for the final render: draft renders half-res (ql)."""
    return "ql" if (profile or "").strip().lower() == "draft" else "qh"


def strict_final_verify_for_profile(profile: str) -> bool:
    """Draft renders are half-res by design — skip the 1080p/fps assertion."""
    return (profile or "").strip().lower() != "draft"
