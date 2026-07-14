"""Voice catalog and per-job voice selection.

The TTS *engine* stays a deployment choice (``VIDEO_API_VOICE_ENGINE``), but the
*voice* is a per-request choice. This module is the single source of truth for
"which voices exist for which engine":

- ``kokoro``  -> curated list of the best-graded Kokoro voices, restricted to
  the languages the pipeline actually maps to Kokoro lang codes (EN + FR).
- ``openai``  -> the classic voices of the ``/audio/speech`` API; override the
  list with ``VIDEO_API_OPENAI_TTS_VOICES`` for OpenAI-compatible servers that
  expose different names.
- ``moss`` (local and ``moss-remote``) -> MOSS-TTS has no named voices; a
  "voice" is a reference WAV in the voice bank (``VIDEO_API_VOICE_BANK_DIR``):
  ``<id>.wav`` plus an optional ``<id>.json`` sidecar (label, description,
  languages, reference_text). Selecting one also pins the otherwise stochastic
  first-segment timbre (without a reference, MOSS samples a random timbre on
  the first segment and clones it for the rest of the job).
- ``chatterbox`` -> single built-in timbre, nothing selectable.

A requested voice is validated at request time (clean HTTP 422) and re-resolved
in the worker right before the per-job settings snapshot is frozen; a voice
that disappeared between the two fails the job clearly instead of silently
falling back to another timbre.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from video_api.config import Settings, apply_quality_profile
from video_api.languages import normalize_language

logger = logging.getLogger(__name__)


class VoiceSelectionError(ValueError):
    """Requested voice cannot be honored (unknown id, wrong engine/language)."""


@dataclass(frozen=True)
class Voice:
    id: str
    label: str
    engine: str  # canonical family: "kokoro" | "openai" | "moss"
    # None = works for every language the API accepts (voice cloning / true
    # multilingual voices). Otherwise the normalized language codes it supports.
    languages: tuple[str, ...] | None
    description: str = ""
    # moss bank voices only: absolute path of the reference WAV (and optional
    # transcript) forwarded to the local engine or uploaded to the GPU server.
    reference_audio: str = ""
    reference_text: str = ""


QUALITY_PROFILES = ("draft", "standard", "high", "final")

# Kokoro voices, curated by the upstream quality grades (hexgrad/Kokoro-82M
# VOICES.md). British voices are excluded on purpose: the generator maps
# en -> lang_code "a" (American G2P), so bf_*/bm_* would be mispronounced.
KOKORO_VOICES: tuple[Voice, ...] = (
    Voice("af_heart", "Heart — femme (EN)", "kokoro", ("en",), "Voix féminine américaine, la mieux notée du catalogue Kokoro."),
    Voice("af_bella", "Bella — femme (EN)", "kokoro", ("en",), "Voix féminine américaine chaleureuse (défaut historique du pipeline)."),
    Voice("af_nicole", "Nicole — femme (EN)", "kokoro", ("en",), "Voix féminine américaine posée, proche du chuchotement."),
    Voice("af_sarah", "Sarah — femme (EN)", "kokoro", ("en",), "Voix féminine américaine neutre."),
    Voice("am_michael", "Michael — homme (EN)", "kokoro", ("en",), "Voix masculine américaine grave."),
    Voice("am_fenrir", "Fenrir — homme (EN)", "kokoro", ("en",), "Voix masculine américaine énergique."),
    Voice("am_puck", "Puck — homme (EN)", "kokoro", ("en",), "Voix masculine américaine claire."),
    Voice("ff_siwis", "Siwis — femme (FR)", "kokoro", ("fr",), "Seule voix française du catalogue Kokoro."),
)

# Baseline of the OpenAI /audio/speech API (supported by tts-1 and gpt-4o
# family models alike). All are multilingual.
OPENAI_DEFAULT_VOICES: tuple[str, ...] = ("alloy", "echo", "fable", "onyx", "nova", "shimmer")

_BANK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def voice_family(engine: str) -> str:
    """Canonical engine family used by the catalog (moss-remote -> moss)."""
    normalized = (engine or "").strip().lower()
    if normalized in {"chatterbox", "local", "command"}:
        return "chatterbox"
    if normalized == "kokoro":
        return "kokoro"
    if normalized in {"moss", "moss-tts", "moss_tts", "moss-remote", "moss_remote", "remote-moss"}:
        return "moss"
    if normalized in {"openai", "openai-compatible", "openai_compatible"}:
        return "openai"
    return normalized


def engine_family_for_profile(settings: Settings, profile: str | None) -> str:
    """Engine family that will actually synthesize for a given quality profile
    (the draft profile overrides the configured engine with Kokoro)."""
    return voice_family(apply_quality_profile(settings, profile or "standard").voice_engine)


def openai_voices(settings: Settings) -> tuple[Voice, ...]:
    raw = settings.openai_tts_voices.strip()
    names = (
        tuple(name.strip() for name in raw.split(",") if name.strip())
        if raw
        else OPENAI_DEFAULT_VOICES
    )
    return tuple(
        Voice(name, name.capitalize(), "openai", None, "Voix du serveur TTS OpenAI-compatible configuré.")
        for name in names
    )


def _load_bank_sidecar(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("voices.bank.sidecar_invalid path=%s error=%s", path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def _sidecar_languages(raw: object, voice_id: str) -> tuple[str, ...] | None:
    if not isinstance(raw, list) or not raw:
        return None
    codes: list[str] = []
    for item in raw:
        try:
            code = normalize_language(str(item))
        except ValueError:
            logger.warning("voices.bank.language_ignored voice=%s language=%r", voice_id, item)
            continue
        if code not in codes:
            codes.append(code)
    return tuple(codes) or None


def moss_voices(settings: Settings) -> tuple[Voice, ...]:
    """Scan the voice bank for reference WAVs. Missing directory = no voices
    (deployments without a bank simply keep MOSS's free-running timbre)."""
    bank_dir = Path(settings.voice_bank_dir)
    if not bank_dir.is_dir():
        return ()
    voices: list[Voice] = []
    for wav_path in sorted(bank_dir.glob("*.wav")):
        voice_id = wav_path.stem
        if not _BANK_ID_RE.match(voice_id):
            logger.warning("voices.bank.id_ignored path=%s", wav_path)
            continue
        sidecar = _load_bank_sidecar(wav_path.with_suffix(".json")) if wav_path.with_suffix(".json").exists() else {}
        voices.append(
            Voice(
                id=voice_id,
                label=str(sidecar.get("label") or voice_id.replace("_", " ").replace("-", " ").title()),
                engine="moss",
                languages=_sidecar_languages(sidecar.get("languages"), voice_id),
                description=str(sidecar.get("description") or "Voix clonée depuis un WAV de référence de la banque de voix."),
                reference_audio=str(wav_path.resolve()),
                reference_text=str(sidecar.get("reference_text") or ""),
            )
        )
    return tuple(voices)


def voices_for_family(settings: Settings, family: str) -> tuple[Voice, ...]:
    if family == "kokoro":
        return KOKORO_VOICES
    if family == "openai":
        return openai_voices(settings)
    if family == "moss":
        return moss_voices(settings)
    return ()


def _default_voice_id(settings: Settings, family: str) -> str:
    if family == "kokoro":
        return settings.kokoro_voice
    if family == "openai":
        return settings.openai_tts_voice
    if family == "moss" and settings.moss_tts_reference_audio.strip():
        return Path(settings.moss_tts_reference_audio).stem
    return ""


def resolve_voice(
    settings: Settings, profile: str | None, voice_id: str, languages: list[str]
) -> Voice:
    """Validate a requested voice against the engine that will actually run for
    this profile and every requested language. Raises VoiceSelectionError with
    an actionable message (surfaced as HTTP 422 at the API boundary)."""
    family = engine_family_for_profile(settings, profile)
    if family == "chatterbox":
        raise VoiceSelectionError(
            "le moteur vocal 'chatterbox' n'expose pas de voix sélectionnable; "
            "retirez le champ 'voice' ou configurez un autre moteur TTS"
        )
    candidates = voices_for_family(settings, family)
    if not candidates:
        raise VoiceSelectionError(
            f"aucune voix disponible pour le moteur '{family}'"
            + (" (banque de voix vide — déposez un WAV de référence dans "
               f"{settings.voice_bank_dir})" if family == "moss" else "")
        )
    voice = next((item for item in candidates if item.id == voice_id), None)
    if voice is None:
        available = ", ".join(item.id for item in candidates)
        raise VoiceSelectionError(
            f"voix inconnue {voice_id!r} pour le moteur '{family}'"
            f" (profil de qualité: la sélection s'applique au moteur réellement utilisé);"
            f" voix disponibles: {available}"
        )
    if voice.languages is not None:
        unsupported = [code for code in languages if code not in voice.languages]
        if unsupported:
            raise VoiceSelectionError(
                f"la voix {voice_id!r} ne couvre pas la/les langue(s) {', '.join(unsupported)}"
                f" (langues supportées: {', '.join(voice.languages)})"
            )
    return voice


def apply_voice_settings(settings: Settings, voice: Voice) -> Settings:
    """Freeze the chosen voice into the per-job settings snapshot. Every field
    touched here already feeds voice_command_for_settings/voice_signature, so
    the per-segment audio cache invalidates correctly on a voice change."""
    if voice.engine == "kokoro":
        return dataclasses.replace(settings, kokoro_voice=voice.id)
    if voice.engine == "openai":
        return dataclasses.replace(settings, openai_tts_voice=voice.id)
    if voice.engine == "moss":
        return dataclasses.replace(
            settings,
            moss_tts_reference_audio=voice.reference_audio,
            moss_tts_reference_text=voice.reference_text,
        )
    raise VoiceSelectionError(f"moteur vocal sans voix applicable: {voice.engine!r}")


def apply_job_voice(settings: Settings, voice_id: str | None) -> Settings:
    """Worker-side resolution, called on the profile+language-adjusted settings.

    With an explicit voice: re-resolve it against the effective engine (the WAV
    may have been deleted since the request was accepted) and fail clearly.
    Without one: keep the configured defaults, except the one genuinely broken
    case — Kokoro speaking a language its configured default voice does not
    cover (e.g. af_bella on a French job) — where the first catalog voice of
    that language is promoted instead.
    """
    family = voice_family(settings.voice_engine)
    if voice_id:
        candidates = voices_for_family(settings, family)
        voice = next((item for item in candidates if item.id == voice_id), None)
        if voice is None:
            raise VoiceSelectionError(
                f"la voix {voice_id!r} demandée à la création n'est plus disponible "
                f"pour le moteur '{family}'"
            )
        if family == "moss" and not Path(voice.reference_audio).is_file():
            raise VoiceSelectionError(
                f"le WAV de référence de la voix {voice_id!r} est introuvable: {voice.reference_audio}"
            )
        return apply_voice_settings(settings, voice)

    if family == "kokoro":
        language = normalize_language(settings.voice_language)
        configured = next((v for v in KOKORO_VOICES if v.id == settings.kokoro_voice), None)
        if configured is not None and configured.languages and language not in configured.languages:
            fallback = next((v for v in KOKORO_VOICES if v.languages and language in v.languages), None)
            if fallback is not None:
                logger.info(
                    "voices.kokoro.language_default voice=%s language=%s replaces=%s",
                    fallback.id,
                    language,
                    settings.kokoro_voice,
                )
                return dataclasses.replace(settings, kokoro_voice=fallback.id)
    return settings


def voices_payload(settings: Settings) -> dict:
    """Data for GET /v1/voices: the effective engine per quality profile and
    every voice selectable on at least one profile."""
    engine_by_profile = {
        profile: engine_family_for_profile(settings, profile) for profile in QUALITY_PROFILES
    }
    families: list[str] = []
    for family in engine_by_profile.values():
        if family != "chatterbox" and family not in families:
            families.append(family)
    voices = []
    for family in families:
        default_id = _default_voice_id(settings, family)
        for voice in voices_for_family(settings, family):
            voices.append(
                {
                    "id": voice.id,
                    "label": voice.label,
                    "engine": voice.engine,
                    "languages": list(voice.languages) if voice.languages is not None else None,
                    "description": voice.description,
                    "is_default": voice.id == default_id,
                }
            )
    return {
        "engine": engine_by_profile["standard"],
        "engine_by_profile": engine_by_profile,
        "voices": voices,
    }
