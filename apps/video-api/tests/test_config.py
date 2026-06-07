from __future__ import annotations

from video_api import config
from video_api.config import Settings


def test_settings_reads_environment_when_instantiated(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.test/v1")
    settings = Settings()

    assert settings.openai_base_url == "https://example.test/v1"


def test_settings_reads_openai_tts_environment(monkeypatch):
    monkeypatch.setenv("VIDEO_API_VOICE_ENGINE", "openai")
    monkeypatch.setenv("VIDEO_API_OPENAI_TTS_MODEL", "local-tts")
    monkeypatch.setenv("VIDEO_API_OPENAI_TTS_VOICE", "narrator")
    monkeypatch.setenv("VIDEO_API_OPENAI_TTS_FORMAT", "wav")
    monkeypatch.setenv("VIDEO_API_OPENAI_TTS_SPEED", "0.95")

    settings = Settings()

    assert settings.voice_engine == "openai"
    assert settings.openai_tts_model == "local-tts"
    assert settings.openai_tts_voice == "narrator"
    assert settings.openai_tts_format == "wav"
    assert settings.openai_tts_speed == 0.95


def test_dotenv_loads_missing_values_without_overriding(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "OPENAI_BASE_URL=https://from-file.test/v1",
                "OPENAI_MODEL='model-from-file'",
                "OPENAI_API_KEY=key-from-file # inline comment",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("VIDEO_API_ENV_FILE", str(env_file))
    monkeypatch.setenv("OPENAI_MODEL", "model-from-process")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    config._load_dotenv_if_present()

    assert Settings().openai_base_url == "https://from-file.test/v1"
    assert Settings().openai_model == "model-from-process"
    assert Settings().openai_api_key == "key-from-file"
