"""Voice catalog, per-request selection and the GET /v1/voices endpoint."""
from __future__ import annotations

import dataclasses
import json

import pytest
from fastapi.testclient import TestClient

import video_api.main as main_module
from video_api.config import Settings
from video_api.db import SessionLocal
from video_api.models import VideoJob
from video_api.pipeline.voice import voice_signature
from video_api.voices import (
    KOKORO_VOICES,
    VoiceSelectionError,
    apply_job_voice,
    engine_family_for_profile,
    moss_voices,
    openai_voices,
    resolve_voice,
    voices_payload,
)


def _bank(tmp_path, *names: str):
    bank = tmp_path / "voice-bank"
    bank.mkdir(exist_ok=True)
    for name in names:
        (bank / f"{name}.wav").write_bytes(b"RIFFfakewav")
    return bank


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

def test_kokoro_catalog_covers_en_and_fr() -> None:
    languages = {code for voice in KOKORO_VOICES for code in (voice.languages or ())}
    assert languages == {"en", "fr"}
    assert any(voice.id == "ff_siwis" for voice in KOKORO_VOICES)


def test_openai_voices_default_and_env_override() -> None:
    default_ids = [voice.id for voice in openai_voices(Settings())]
    assert "alloy" in default_ids and "nova" in default_ids
    custom = openai_voices(Settings(openai_tts_voices="narrator, calm-fr"))
    assert [voice.id for voice in custom] == ["narrator", "calm-fr"]
    assert all(voice.languages is None for voice in custom)


def test_moss_bank_scan_reads_sidecar_and_ignores_bad_ids(tmp_path) -> None:
    bank = _bank(tmp_path, "sarah")
    (bank / "sarah.json").write_text(
        json.dumps(
            {
                "label": "Sarah — femme (FR)",
                "description": "Voix posée.",
                "languages": ["fr", "EN", "not-a-language"],
                "reference_text": "Bonjour et bienvenue.",
            }
        ),
        encoding="utf-8",
    )
    (bank / "bad name.wav").write_bytes(b"RIFF")  # invalid id -> skipped

    voices = moss_voices(Settings(voice_bank_dir=str(bank)))

    assert [voice.id for voice in voices] == ["sarah"]
    voice = voices[0]
    assert voice.label == "Sarah — femme (FR)"
    assert voice.languages == ("fr", "en")
    assert voice.reference_text == "Bonjour et bienvenue."
    assert voice.reference_audio.endswith("sarah.wav")


def test_moss_bank_missing_directory_means_no_voices(tmp_path) -> None:
    assert moss_voices(Settings(voice_bank_dir=str(tmp_path / "nope"))) == ()


# ---------------------------------------------------------------------------
# Request-time resolution
# ---------------------------------------------------------------------------

def test_draft_profile_resolves_to_kokoro_even_on_moss_deployment() -> None:
    settings = Settings(voice_engine="moss-remote")
    assert engine_family_for_profile(settings, "standard") == "moss"
    assert engine_family_for_profile(settings, "draft") == "kokoro"


def test_resolve_voice_unknown_id_lists_available() -> None:
    settings = Settings(voice_engine="kokoro")
    with pytest.raises(VoiceSelectionError, match="af_bella"):
        resolve_voice(settings, "standard", "does_not_exist", ["en"])


def test_resolve_voice_rejects_language_mismatch() -> None:
    settings = Settings(voice_engine="kokoro")
    with pytest.raises(VoiceSelectionError, match="fr"):
        resolve_voice(settings, "standard", "af_bella", ["en", "fr"])
    assert resolve_voice(settings, "standard", "ff_siwis", ["fr"]).id == "ff_siwis"


def test_resolve_voice_rejects_chatterbox() -> None:
    with pytest.raises(VoiceSelectionError, match="chatterbox"):
        resolve_voice(Settings(voice_engine="chatterbox"), "standard", "anything", ["en"])


def test_resolve_voice_applies_to_draft_engine(tmp_path) -> None:
    bank = _bank(tmp_path, "sarah")
    settings = Settings(voice_engine="moss-remote", voice_bank_dir=str(bank))
    assert resolve_voice(settings, "standard", "sarah", ["fr"]).id == "sarah"
    # Under draft the effective engine is Kokoro: the moss voice must be refused.
    with pytest.raises(VoiceSelectionError, match="kokoro"):
        resolve_voice(settings, "draft", "sarah", ["fr"])


# ---------------------------------------------------------------------------
# Worker-side application
# ---------------------------------------------------------------------------

def test_apply_job_voice_moss_sets_reference_and_changes_signature(tmp_path) -> None:
    bank = _bank(tmp_path, "sarah")
    settings = Settings(voice_engine="moss", voice_bank_dir=str(bank))
    adjusted = apply_job_voice(settings, "sarah")
    assert adjusted.moss_tts_reference_audio.endswith("sarah.wav")
    # The chosen voice must invalidate the per-segment audio cache.
    assert voice_signature(adjusted) != voice_signature(settings)


def test_apply_job_voice_fails_clearly_when_wav_disappeared(tmp_path) -> None:
    bank = _bank(tmp_path, "sarah")
    settings = Settings(voice_engine="moss", voice_bank_dir=str(bank))
    (bank / "sarah.wav").unlink()
    with pytest.raises(VoiceSelectionError, match="sarah"):
        apply_job_voice(settings, "sarah")


def test_apply_job_voice_kokoro_picks_language_default_without_request() -> None:
    settings = Settings(voice_engine="kokoro", kokoro_voice="af_bella", voice_language="fr")
    adjusted = apply_job_voice(settings, None)
    assert adjusted.kokoro_voice == "ff_siwis"
    # English keeps the configured default untouched.
    settings_en = Settings(voice_engine="kokoro", kokoro_voice="af_bella", voice_language="en")
    assert apply_job_voice(settings_en, None) is settings_en


def test_apply_job_voice_explicit_kokoro_choice() -> None:
    settings = Settings(voice_engine="kokoro", voice_language="en")
    adjusted = apply_job_voice(settings, "am_michael")
    assert adjusted.kokoro_voice == "am_michael"


# ---------------------------------------------------------------------------
# GET /v1/voices payload
# ---------------------------------------------------------------------------

def test_voices_payload_lists_active_and_draft_engines(tmp_path) -> None:
    bank = _bank(tmp_path, "sarah")
    settings = Settings(voice_engine="moss-remote", voice_bank_dir=str(bank))
    payload = voices_payload(settings)
    assert payload["engine"] == "moss"
    assert payload["engine_by_profile"]["draft"] == "kokoro"
    engines = {voice["engine"] for voice in payload["voices"]}
    assert engines == {"moss", "kokoro"}


def test_voices_payload_marks_configured_default() -> None:
    settings = Settings(voice_engine="kokoro", kokoro_voice="af_heart")
    payload = voices_payload(settings)
    defaults = [voice["id"] for voice in payload["voices"] if voice["is_default"]]
    assert defaults == ["af_heart"]


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------

class _StubAsyncResult:
    id = "stub-task-id"


class _StubTask:
    def delay(self, job_id: str) -> _StubAsyncResult:  # noqa: ARG002
        return _StubAsyncResult()


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(main_module, "run_video_job", _StubTask())
    with TestClient(main_module.app) as test_client:
        yield test_client


def _use_engine(monkeypatch, **overrides) -> None:
    monkeypatch.setattr(
        main_module, "settings", dataclasses.replace(main_module.settings, **overrides)
    )


def test_voices_endpoint_lists_kokoro(client: TestClient, monkeypatch) -> None:
    _use_engine(monkeypatch, voice_engine="kokoro")
    response = client.get("/v1/voices")
    assert response.status_code == 200
    body = response.json()
    assert body["engine"] == "kokoro"
    assert any(voice["id"] == "ff_siwis" for voice in body["voices"])


def test_create_with_valid_voice_persists_it(client: TestClient, monkeypatch) -> None:
    _use_engine(monkeypatch, voice_engine="kokoro")
    response = client.post(
        "/v1/videos",
        json={
            "prompt": "Explain how virtual memory and page tables work together",
            "voice": "am_michael",
        },
    )
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    with SessionLocal() as session:
        job = session.get(VideoJob, job_id)
        config = json.loads(job.production_config)
    assert config["voice"] == "am_michael"


def test_create_with_unknown_voice_is_422(client: TestClient, monkeypatch) -> None:
    _use_engine(monkeypatch, voice_engine="kokoro")
    response = client.post(
        "/v1/videos",
        json={
            "prompt": "Explain how virtual memory and page tables work together",
            "voice": "does_not_exist",
        },
    )
    assert response.status_code == 422
    assert "voix inconnue" in response.json()["detail"]


def test_batch_voice_must_cover_every_language(client: TestClient, monkeypatch) -> None:
    _use_engine(monkeypatch, voice_engine="kokoro")
    response = client.post(
        "/v1/videos",
        json={
            "prompt": "Explain how virtual memory and page tables work together",
            "languages": ["en", "fr"],
            "voice": "af_bella",
        },
    )
    assert response.status_code == 422
    assert "fr" in response.json()["detail"]
