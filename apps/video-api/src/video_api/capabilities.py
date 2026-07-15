"""Effective deployment capabilities for GET /v1/capabilities.

The create request accepts many knobs whose real behaviour depends on the
server's environment (.env): the TTS engine limits which languages can be
spoken, research and stock media need a configured provider, the "high"
quality profile only adds something when a vision model exists, and the
render engine has a deployment default. This module derives all of that from
one Settings snapshot so clients (Studio in particular) can build their UI
from the actual platform state instead of hardcoding assumptions.

No secrets leave this module: provider *names* are exposed, keys never.
"""
from __future__ import annotations

from video_api.config import Settings
from video_api.languages import SUPPORTED_LANGUAGES
from video_api.schemas import (
    DURATION_MAX_SECONDS,
    DURATION_MIN_SECONDS,
    MAX_BATCH_LANGUAGES,
    PROMPT_MAX_CHARS,
    RESEARCH_SOURCES_DEFAULT,
    RESEARCH_SOURCES_MAX,
    RESEARCH_SOURCES_MIN,
    THEME_MAX_CHARS,
    VISUAL_ASSETS_DEFAULT,
    VISUAL_ASSETS_MAX,
    VISUAL_ASSETS_MIN,
)
from video_api.voices import (
    KOKORO_VOICES,
    QUALITY_PROFILES,
    engine_family_for_profile,
    voices_for_family,
)

RENDER_ENGINES = ("manim", "remotion")

# Languages each TTS family can actually speak. None = every language the API
# accepts (SUPPORTED_LANGUAGES). Kokoro derives from its curated catalog so the
# two can never drift apart; Chatterbox ships an English-only model.
_KOKORO_LANGUAGES = tuple(
    sorted({code for voice in KOKORO_VOICES for code in (voice.languages or ())})
)
_FAMILY_LANGUAGES: dict[str, tuple[str, ...] | None] = {
    "chatterbox": ("en",),
    "kokoro": _KOKORO_LANGUAGES,
}


def languages_for_family(family: str) -> list[str]:
    """Language codes the family can speak, in SUPPORTED_LANGUAGES order."""
    allowed = _FAMILY_LANGUAGES.get(family)
    if allowed is None:
        return list(SUPPORTED_LANGUAGES)
    return [code for code in SUPPORTED_LANGUAGES if code in allowed]


def _provider_feature(provider: str) -> dict:
    normalized = (provider or "").strip().lower()
    available = normalized not in {"", "none"}
    return {"available": available, "provider": normalized if available else None}


def capabilities_payload(settings: Settings) -> dict:
    engine_by_profile = {
        profile: engine_family_for_profile(settings, profile) for profile in QUALITY_PROFILES
    }
    languages_by_profile = {
        profile: languages_for_family(family) for profile, family in engine_by_profile.items()
    }
    voice_selection_by_profile = {
        profile: len(voices_for_family(settings, family)) > 0
        for profile, family in engine_by_profile.items()
    }
    return {
        "engine": engine_by_profile["standard"],
        "engine_by_profile": engine_by_profile,
        "languages": [
            {"code": code, "name": name} for code, name in SUPPORTED_LANGUAGES.items()
        ],
        "languages_by_profile": languages_by_profile,
        "voice_selection_by_profile": voice_selection_by_profile,
        "render_engines": list(RENDER_ENGINES),
        "features": {
            "research": _provider_feature(settings.research_provider),
            "stock_assets": _provider_feature(settings.asset_provider),
            "visual_review": {
                "available": bool(settings.visual_review_model.strip()),
                "provider": None,
            },
        },
        "limits": {
            "prompt_max_chars": PROMPT_MAX_CHARS,
            "theme_max_chars": THEME_MAX_CHARS,
            "max_batch_languages": MAX_BATCH_LANGUAGES,
            "target_duration_seconds": {
                "min": DURATION_MIN_SECONDS,
                "max": DURATION_MAX_SECONDS,
                # The env default is a free integer; keep the advertised default
                # inside the accepted request window.
                "default": min(
                    max(settings.default_target_duration_seconds, DURATION_MIN_SECONDS),
                    DURATION_MAX_SECONDS,
                ),
            },
            "research_max_sources": {
                "min": RESEARCH_SOURCES_MIN,
                "max": RESEARCH_SOURCES_MAX,
                "default": RESEARCH_SOURCES_DEFAULT,
            },
            "visuals_max_assets": {
                "min": VISUAL_ASSETS_MIN,
                "max": VISUAL_ASSETS_MAX,
                "default": VISUAL_ASSETS_DEFAULT,
            },
        },
        "defaults": {
            "production_mode": settings.production_mode,
            "caption_mode": settings.caption_mode,
            "quality_profile": "standard",
            "render_engine": settings.render_engine,
        },
    }
