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


def test_settings_reads_moss_tts_environment(monkeypatch):
    monkeypatch.setenv("VIDEO_API_VOICE_ENGINE", "moss")
    monkeypatch.setenv("VIDEO_API_MOSS_TTS_MODEL", "OpenMOSS-Team/MOSS-TTS-v1.5")
    monkeypatch.setenv("VIDEO_API_MOSS_TTS_VOICE", "speaker-a")
    monkeypatch.setenv("VIDEO_API_MOSS_TTS_REFERENCE_AUDIO", "/data/ref.wav")
    monkeypatch.setenv("VIDEO_API_MOSS_TTS_REFERENCE_TEXT", "Reference text")
    monkeypatch.setenv("VIDEO_API_MOSS_TTS_CONSISTENT_VOICE", "0")
    monkeypatch.setenv("VIDEO_API_MOSS_TTS_DEVICE", "cpu")
    monkeypatch.setenv("VIDEO_API_MOSS_TTS_DTYPE", "bfloat16")
    monkeypatch.setenv("VIDEO_API_MOSS_TTS_COMMAND", "python -m moss_tts --output {output}")

    settings = Settings()

    assert settings.voice_engine == "moss"
    assert settings.moss_tts_model == "OpenMOSS-Team/MOSS-TTS-v1.5"
    assert settings.moss_tts_voice == "speaker-a"
    assert settings.moss_tts_reference_audio == "/data/ref.wav"
    assert settings.moss_tts_reference_text == "Reference text"
    assert settings.moss_tts_consistent_voice is False
    assert settings.moss_tts_device == "cpu"
    assert settings.moss_tts_dtype == "bfloat16"
    assert settings.moss_tts_command == "python -m moss_tts --output {output}"


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
