from __future__ import annotations

from video_api.config import Settings
from video_api.pipeline.production import voice_command_for_settings


def test_chatterbox_voice_engine_uses_configured_command() -> None:
    settings = Settings(
        voice_engine="chatterbox",
        voice_command="python generate_voice_en.py --engine chatterbox --tail-padding 0.45",
    )

    args, env = voice_command_for_settings(settings)

    assert args == ["python", "generate_voice_en.py", "--engine", "chatterbox", "--tail-padding", "0.45"]
    assert env is None


def test_openai_voice_engine_uses_same_endpoint_without_logging_secret() -> None:
    settings = Settings(
        voice_engine="openai",
        openai_base_url="https://llm.example.test/v1",
        openai_api_key="secret-key",
        openai_tts_model="local-tts",
        openai_tts_voice="narrator",
        openai_tts_format="wav",
        openai_tts_speed=0.9,
        voice_tail_padding=0.35,
    )

    args, env = voice_command_for_settings(settings)

    assert args == [
        "python",
        "generate_voice_en.py",
        "--engine",
        "openai",
        "--tail-padding",
        "0.350",
    ]
    assert "secret-key" not in " ".join(args)
    assert env == {
        "OPENAI_BASE_URL": "https://llm.example.test/v1",
        "OPENAI_API_KEY": "secret-key",
        "VIDEO_API_OPENAI_TTS_MODEL": "local-tts",
        "VIDEO_API_OPENAI_TTS_VOICE": "narrator",
        "VIDEO_API_OPENAI_TTS_FORMAT": "wav",
        "VIDEO_API_OPENAI_TTS_SPEED": "0.9",
    }


def test_moss_voice_engine_uses_job_language_and_model_env() -> None:
    settings = Settings(
        voice_engine="moss",
        voice_language="fr",
        moss_tts_model="OpenMOSS-Team/MOSS-TTS-v1.5",
        moss_tts_voice="narrator",
        moss_tts_reference_audio="/data/voice/ref.wav",
        moss_tts_reference_text="Bonjour tout le monde.",
        moss_tts_device="cpu",
        moss_tts_dtype="bfloat16",
        moss_tts_command="python -m moss_tts --text-file {text_file} --output {output}",
        voice_tail_padding=0.4,
    )

    args, env = voice_command_for_settings(settings)

    assert args == [
        "python",
        "generate_voice_en.py",
        "--engine",
        "moss",
        "--moss-model",
        "OpenMOSS-Team/MOSS-TTS-v1.5",
        "--moss-language",
        "fr",
        "--moss-dtype",
        "bfloat16",
        "--tail-padding",
        "0.400",
    ]
    assert env == {
        "VIDEO_API_MOSS_TTS_MODEL": "OpenMOSS-Team/MOSS-TTS-v1.5",
        "VIDEO_API_MOSS_TTS_LANGUAGE": "fr",
        "VIDEO_API_MOSS_TTS_VOICE": "narrator",
        "VIDEO_API_MOSS_TTS_REFERENCE_AUDIO": "/data/voice/ref.wav",
        "VIDEO_API_MOSS_TTS_REFERENCE_TEXT": "Bonjour tout le monde.",
        "VIDEO_API_MOSS_TTS_DEVICE": "cpu",
        "VIDEO_API_MOSS_TTS_DTYPE": "bfloat16",
        "VIDEO_API_MOSS_TTS_COMMAND": "python -m moss_tts --text-file {text_file} --output {output}",
    }
