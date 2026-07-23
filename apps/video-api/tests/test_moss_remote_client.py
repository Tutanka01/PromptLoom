from __future__ import annotations

import base64
import importlib.util
import io
import wave
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_VOICE_SCRIPT = (
    _REPO_ROOT
    / "videos"
    / "linux-fondamentaux"
    / "002-c-est-quoi-un-syscall"
    / "generate_voice_en.py"
)


def _load_voice_module():
    spec = importlib.util.spec_from_file_location("reference_generate_voice_en", _VOICE_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SEGMENTS = [
    {"key": "Scene1", "text": "Premier segment."},
    {"key": "Scene2", "text": "Deuxieme segment."},
]


def _wav_bytes(
    *,
    channels: int = 1,
    sample_width: int = 2,
    sample_rate: int = 24000,
    frames: int = 2400,
) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(sample_width)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00" * frames * channels * sample_width)
    return output.getvalue()


def test_moss_remote_sends_only_missing_segments_and_anchors_to_local_wav(
    monkeypatch, tmp_path: Path
) -> None:
    module = _load_voice_module()
    audio_dir = tmp_path / "audio" / "en"
    audio_dir.mkdir(parents=True)
    (audio_dir / "Scene1.wav").write_bytes(b"RIFFlocal")

    requests: list[tuple[str, str, dict | None]] = []
    events: list[str] = []
    get_count = 0
    states = iter(
        [
            {"job_id": "j1", "status": "queued"},
            {
                "status": "running",
                "segments": [
                    {
                        "key": "Scene2",
                        "status": "done",
                        "cached": False,
                        "duration_seconds": 0.1,
                        "wav_url": "/v1/jobs/j1/audio/Scene2.wav",
                    }
                ],
            },
            {
                "status": "completed",
                "segments": [
                    {
                        "key": "Scene2",
                        "status": "done",
                        "cached": False,
                        "duration_seconds": 0.1,
                        "wav_url": "/v1/jobs/j1/audio/Scene2.wav",
                    }
                ],
            },
        ]
    )

    def fake_request_json(method, url, api_key, payload=None, timeout=120.0):
        nonlocal get_count
        requests.append((method, url, payload))
        if method == "GET":
            get_count += 1
            events.append(f"get:{get_count}")
        return next(states)

    downloads: list[str] = []

    def fake_download_file(url, api_key, dest, timeout=600.0):
        downloads.append(url)
        events.append("download")
        dest.write_bytes(_wav_bytes())

    monkeypatch.setattr(module, "OUT_DIR", audio_dir)
    monkeypatch.setattr(module, "_request_json", fake_request_json)
    monkeypatch.setattr(module, "_download_file", fake_download_file)

    module.generate_moss_remote(
        _SEGMENTS,
        server_url="http://gpu.lan:8100/",
        api_key="secret",
        model_id="OpenMOSS-Team/MOSS-TTS-v1.5",
        language="fr",
        reference_audio="",
        consistent_voice=True,
        force=False,
        timeout_seconds=30,
        poll_seconds=0,
    )

    method, url, payload = requests[0]
    assert (method, url) == ("POST", "http://gpu.lan:8100/v1/tts/batch")
    # Scene1 exists locally: only Scene2 is synthesized remotely, with Scene1's
    # WAV uploaded as the cloning reference so the timbre stays identical.
    assert [segment["key"] for segment in payload["segments"]] == ["Scene2"]
    assert payload["reference_audio_b64"] == base64.b64encode(b"RIFFlocal").decode("ascii")
    assert payload["language"] == "fr"

    assert downloads == ["http://gpu.lan:8100/v1/jobs/j1/audio/Scene2.wav"]
    assert events == ["get:1", "download", "get:2"]
    assert (audio_dir / "Scene2.wav").read_bytes() == _wav_bytes()
    assert not (audio_dir / "Scene2.wav.part").exists()
    assert not (audio_dir / "Scene2.mp3").exists()


def test_moss_remote_skips_server_call_when_everything_is_cached(
    monkeypatch, tmp_path: Path
) -> None:
    module = _load_voice_module()
    audio_dir = tmp_path / "audio" / "en"
    audio_dir.mkdir(parents=True)
    for segment in _SEGMENTS:
        (audio_dir / f"{segment['key']}.wav").write_bytes(b"RIFF")

    def unexpected_request(*args, **kwargs):
        raise AssertionError("server must not be called when all WAVs exist")

    monkeypatch.setattr(module, "OUT_DIR", audio_dir)
    monkeypatch.setattr(module, "_request_json", unexpected_request)

    module.generate_moss_remote(
        _SEGMENTS,
        server_url="http://gpu.lan:8100",
        api_key="",
        model_id="",
        language="en",
        reference_audio="",
        consistent_voice=True,
        force=False,
        timeout_seconds=30,
    )


def test_moss_remote_raises_clear_error_when_job_fails(monkeypatch, tmp_path: Path) -> None:
    module = _load_voice_module()
    audio_dir = tmp_path / "audio" / "en"
    audio_dir.mkdir(parents=True)

    states = iter(
        [
            {"job_id": "j2", "status": "queued"},
            {"status": "failed", "error": "model failed to load: CUDA out of memory"},
        ]
    )
    monkeypatch.setattr(module, "OUT_DIR", audio_dir)
    monkeypatch.setattr(
        module, "_request_json", lambda *args, **kwargs: next(states)
    )

    with pytest.raises(RuntimeError, match="CUDA out of memory"):
        module.generate_moss_remote(
            _SEGMENTS,
            server_url="http://gpu.lan:8100",
            api_key="",
            model_id="",
            language="en",
            reference_audio="",
            consistent_voice=True,
            force=False,
            timeout_seconds=30,
            poll_seconds=0,
        )


def test_moss_remote_still_fails_after_downloading_ready_wav(
    monkeypatch, tmp_path: Path
) -> None:
    module = _load_voice_module()
    audio_dir = tmp_path / "audio" / "en"
    audio_dir.mkdir(parents=True)
    states = iter(
        [
            {"job_id": "j3", "status": "queued"},
            {
                "status": "running",
                "segments": [
                    {
                        "key": "Scene1",
                        "status": "done",
                        "cached": True,
                        "duration_seconds": 0.1,
                        "wav_url": "/v1/jobs/j3/audio/Scene1.wav",
                    },
                    {"key": "Scene2", "status": "running"},
                ],
            },
            {
                "status": "failed",
                "error": "CUDA out of memory",
                "segments": [
                    {
                        "key": "Scene1",
                        "status": "done",
                        "cached": True,
                        "duration_seconds": 0.1,
                        "wav_url": "/v1/jobs/j3/audio/Scene1.wav",
                    },
                    {"key": "Scene2", "status": "failed"},
                ],
            },
        ]
    )

    monkeypatch.setattr(module, "OUT_DIR", audio_dir)
    monkeypatch.setattr(module, "_request_json", lambda *args, **kwargs: next(states))
    monkeypatch.setattr(
        module,
        "_download_file",
        lambda url, api_key, dest, timeout=600.0: dest.write_bytes(_wav_bytes()),
    )

    with pytest.raises(RuntimeError, match="CUDA out of memory"):
        module.generate_moss_remote(
            _SEGMENTS,
            server_url="http://gpu.lan:8100",
            api_key="",
            model_id="",
            language="en",
            reference_audio="",
            consistent_voice=True,
            force=False,
            timeout_seconds=30,
            poll_seconds=0,
        )

    assert (audio_dir / "Scene1.wav").exists()
    assert not (audio_dir / "Scene2.wav").exists()


def test_download_moss_wav_publishes_valid_file_atomically(
    monkeypatch, tmp_path: Path
) -> None:
    module = _load_voice_module()
    destination = tmp_path / "Scene1.wav"
    monkeypatch.setattr(
        module,
        "_download_file",
        lambda url, api_key, dest, timeout=600.0: dest.write_bytes(_wav_bytes()),
    )

    module._download_moss_wav_atomic(
        "http://gpu.lan/Scene1.wav",
        "",
        destination,
        expected_duration=0.1,
    )

    assert destination.read_bytes() == _wav_bytes()
    assert not (tmp_path / "Scene1.wav.part").exists()


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"not-a-wav", "header"),
        (_wav_bytes(sample_width=1), "PCM16"),
        (_wav_bytes(channels=2), "channels"),
        (_wav_bytes(sample_rate=16000), "sample rate"),
        (_wav_bytes()[:-10], "Truncated"),
    ],
)
def test_download_moss_wav_rejects_invalid_file_without_replacing_destination(
    monkeypatch,
    tmp_path: Path,
    payload: bytes,
    message: str,
) -> None:
    module = _load_voice_module()
    destination = tmp_path / "Scene1.wav"
    destination.write_bytes(b"existing-valid-audio")
    monkeypatch.setattr(
        module,
        "_download_file",
        lambda url, api_key, dest, timeout=600.0: dest.write_bytes(payload),
    )

    with pytest.raises(RuntimeError, match=message):
        module._download_moss_wav_atomic("http://gpu.lan/Scene1.wav", "", destination)

    assert destination.read_bytes() == b"existing-valid-audio"
    assert not (tmp_path / "Scene1.wav.part").exists()
