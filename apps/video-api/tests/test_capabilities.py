"""Effective deployment capabilities and the GET /v1/capabilities endpoint."""
from __future__ import annotations

import dataclasses

import pytest
from fastapi.testclient import TestClient

import video_api.main as main_module
from video_api.capabilities import capabilities_payload, languages_for_family
from video_api.config import Settings
from video_api.languages import SUPPORTED_LANGUAGES


# ---------------------------------------------------------------------------
# Payload derivation
# ---------------------------------------------------------------------------

def test_languages_follow_the_effective_engine_per_profile(tmp_path) -> None:
    # MOSS deployment: standard speaks every supported language, draft falls
    # back to Kokoro which only covers EN + FR.
    payload = capabilities_payload(
        Settings(voice_engine="moss-remote", voice_bank_dir=str(tmp_path / "empty"))
    )
    assert payload["engine"] == "moss"
    assert payload["languages_by_profile"]["standard"] == list(SUPPORTED_LANGUAGES)
    assert payload["languages_by_profile"]["draft"] == ["en", "fr"]


def test_chatterbox_is_english_only_and_offers_no_voice_selection() -> None:
    payload = capabilities_payload(Settings(voice_engine="chatterbox"))
    assert payload["languages_by_profile"]["standard"] == ["en"]
    assert payload["voice_selection_by_profile"]["standard"] is False
    # Draft still forces Kokoro, which does expose voices.
    assert payload["voice_selection_by_profile"]["draft"] is True


def test_languages_for_family_defaults_to_full_catalog() -> None:
    assert languages_for_family("moss") == list(SUPPORTED_LANGUAGES)
    assert languages_for_family("openai") == list(SUPPORTED_LANGUAGES)
    assert languages_for_family("kokoro") == ["en", "fr"]


def test_features_reflect_configured_providers() -> None:
    bare = capabilities_payload(Settings())
    assert bare["features"]["research"] == {"available": False, "provider": None}
    assert bare["features"]["stock_assets"] == {"available": False, "provider": None}
    assert bare["features"]["visual_review"]["available"] is False

    configured = capabilities_payload(
        Settings(
            research_provider="tavily",
            asset_provider="pexels",
            visual_review_model="qwen2.5-vl",
        )
    )
    assert configured["features"]["research"] == {"available": True, "provider": "tavily"}
    assert configured["features"]["stock_assets"] == {"available": True, "provider": "pexels"}
    assert configured["features"]["visual_review"]["available"] is True


def test_limits_and_defaults_are_advertised() -> None:
    payload = capabilities_payload(Settings())
    assert payload["limits"]["prompt_max_chars"] == 4000
    assert payload["limits"]["max_batch_languages"] == 8
    duration = payload["limits"]["target_duration_seconds"]
    assert duration["min"] == 20 and duration["max"] == 900
    assert duration["min"] <= duration["default"] <= duration["max"]
    assert payload["defaults"]["quality_profile"] == "standard"
    assert payload["defaults"]["render_engine"] in payload["render_engines"]


def test_out_of_window_env_duration_default_is_clamped() -> None:
    payload = capabilities_payload(Settings(default_target_duration_seconds=10_000))
    assert payload["limits"]["target_duration_seconds"]["default"] == 900


# ---------------------------------------------------------------------------
# HTTP endpoint
# ---------------------------------------------------------------------------

@pytest.fixture()
def client() -> TestClient:
    with TestClient(main_module.app) as test_client:
        yield test_client


def test_capabilities_endpoint_matches_settings(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "settings",
        dataclasses.replace(main_module.settings, voice_engine="kokoro", research_provider="none"),
    )
    response = client.get("/v1/capabilities")
    assert response.status_code == 200
    body = response.json()
    assert body["engine"] == "kokoro"
    assert body["languages_by_profile"]["standard"] == ["en", "fr"]
    assert body["features"]["research"]["available"] is False
    assert {lang["code"] for lang in body["languages"]} == set(SUPPORTED_LANGUAGES)


def test_capabilities_endpoint_requires_api_key_when_configured(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(
        main_module,
        "settings",
        dataclasses.replace(main_module.settings, api_keys=("secret",)),
    )
    assert client.get("/v1/capabilities").status_code == 401
    assert client.get("/v1/capabilities", headers={"X-API-Key": "secret"}).status_code == 200
