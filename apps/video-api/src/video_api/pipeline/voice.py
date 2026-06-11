"""Voice command resolution + per-segment TTS cache.

The TTS step (Chatterbox on CPU) dominates job wall time. The copied
``generate_voice_en.py`` already skips a segment whose WAV exists
(``should_skip_existing``), but it cannot know whether the *text* or the voice
parameters changed since that WAV was generated. This module closes that gap:

- ``voice_signature``  -> stable hash of the resolved voice command + env, so a
  change of engine/voice/params invalidates every segment.
- ``prune_stale_audio`` -> called by the materializers *instead of* deleting the
  whole ``audio/`` directory. It removes only the WAV/MP3 of segments whose
  text-or-params hash changed (or that disappeared), and records the new hashes
  in ``audio/en/cache.json``. Surviving WAVs are then reused by the generator,
  so a repair attempt that only rewrites two scenes only re-synthesizes two
  segments.
"""
from __future__ import annotations

import hashlib
import json
import logging
import shlex
from pathlib import Path

from video_api.config import Settings

logger = logging.getLogger(__name__)

CACHE_FILE_NAME = "cache.json"


def voice_command_for_settings(settings: Settings) -> tuple[list[str], dict[str, str] | None]:
    engine = settings.voice_engine.strip().lower()
    if engine in {"chatterbox", "local", "command"}:
        return shlex.split(settings.voice_command), None
    if engine == "kokoro":
        # Kokoro is ~5x real-time on CPU (vs Chatterbox being GPU-oriented) and
        # supports EN + FR. Deps live in the worker image; no env needed.
        return (
            [
                "python",
                "generate_voice_en.py",
                "--engine",
                "kokoro",
                "--kokoro-lang",
                settings.voice_language,
                "--kokoro-voice",
                settings.kokoro_voice,
                "--tail-padding",
                f"{settings.voice_tail_padding:.3f}",
            ],
            None,
        )
    if engine in {"moss", "moss-tts", "moss_tts"}:
        return (
            [
                "python",
                "generate_voice_en.py",
                "--engine",
                "moss",
                "--moss-model",
                settings.moss_tts_model,
                "--moss-language",
                settings.voice_language,
                "--tail-padding",
                f"{settings.voice_tail_padding:.3f}",
            ],
            {
                "VIDEO_API_MOSS_TTS_MODEL": settings.moss_tts_model,
                "VIDEO_API_MOSS_TTS_LANGUAGE": settings.voice_language,
                "VIDEO_API_MOSS_TTS_VOICE": settings.moss_tts_voice,
                "VIDEO_API_MOSS_TTS_REFERENCE_AUDIO": settings.moss_tts_reference_audio,
                "VIDEO_API_MOSS_TTS_REFERENCE_TEXT": settings.moss_tts_reference_text,
                "VIDEO_API_MOSS_TTS_DEVICE": settings.moss_tts_device,
                "VIDEO_API_MOSS_TTS_COMMAND": settings.moss_tts_command,
            },
        )
    if engine in {"openai", "openai-compatible", "openai_compatible"}:
        return (
            [
                "python",
                "generate_voice_en.py",
                "--engine",
                "openai",
                "--tail-padding",
                f"{settings.voice_tail_padding:.3f}",
            ],
            {
                "OPENAI_BASE_URL": settings.openai_base_url or "",
                "OPENAI_API_KEY": settings.openai_api_key or "",
                "VIDEO_API_OPENAI_TTS_MODEL": settings.openai_tts_model,
                "VIDEO_API_OPENAI_TTS_VOICE": settings.openai_tts_voice,
                "VIDEO_API_OPENAI_TTS_FORMAT": settings.openai_tts_format,
                "VIDEO_API_OPENAI_TTS_SPEED": str(settings.openai_tts_speed),
            },
        )
    raise ValueError(
        "Unsupported VIDEO_API_VOICE_ENGINE="
        f"{settings.voice_engine!r}; expected 'chatterbox', 'kokoro', 'moss' or 'openai'."
    )


def voice_signature(settings: Settings) -> str:
    """Stable fingerprint of everything that shapes the synthesized audio."""
    args, env = voice_command_for_settings(settings)
    payload = json.dumps({"args": args, "env": env or {}}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def segment_fingerprint(text: str, signature: str) -> str:
    payload = signature + "\x00" + " ".join(text.split())
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _segment_files(audio_dir: Path, key: str) -> list[Path]:
    return [
        audio_dir / f"{key}.wav",
        audio_dir / f"{key}.mp3",
        audio_dir / f"{key}.padded.wav",
        *audio_dir.glob(f"{key}.openai.*"),
    ]


def prune_stale_audio(video_dir: Path, segments: list[dict], signature: str) -> dict[str, int]:
    """Invalidate cached segment audio whose text or voice params changed.

    *segments* is the ``segments_en.json`` shape: ``[{"key", "text", ...}]``.
    Returns counters (for logs/tests): {"reused": n, "invalidated": n}.
    """
    audio_dir = video_dir / "audio" / "en"
    cache_path = audio_dir / CACHE_FILE_NAME
    old_cache: dict[str, str] = {}
    if cache_path.exists():
        try:
            old_cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            old_cache = {}

    new_cache: dict[str, str] = {}
    reused = 0
    invalidated = 0
    current_keys = set()
    for segment in segments:
        key = segment["key"]
        current_keys.add(key)
        fingerprint = segment_fingerprint(segment["text"], signature)
        new_cache[key] = fingerprint
        wav_path = audio_dir / f"{key}.wav"
        if old_cache.get(key) == fingerprint and wav_path.exists():
            reused += 1
            continue
        if wav_path.exists():
            invalidated += 1
        for path in _segment_files(audio_dir, key):
            path.unlink(missing_ok=True)

    # Segments that no longer exist (scene removed/renamed by a repair attempt).
    for key in set(old_cache) - current_keys:
        for path in _segment_files(audio_dir, key):
            path.unlink(missing_ok=True)

    audio_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(new_cache, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    logger.info(
        "voice.cache video_dir=%s reused=%d invalidated=%d total=%d",
        video_dir,
        reused,
        invalidated,
        len(segments),
    )
    return {"reused": reused, "invalidated": invalidated}
