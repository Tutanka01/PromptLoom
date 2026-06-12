from pathlib import Path

from video_api.config import Settings
from video_api.pipeline.voice import (
    prune_stale_audio,
    segment_fingerprint,
    voice_signature,
)


def _seed_segment(audio_dir: Path, key: str) -> None:
    audio_dir.mkdir(parents=True, exist_ok=True)
    (audio_dir / f"{key}.wav").write_bytes(b"RIFF")
    (audio_dir / f"{key}.mp3").write_bytes(b"ID3")
    (audio_dir / f"{key}.padded.wav").write_bytes(b"RIFF")


def test_unchanged_segment_is_reused(tmp_path: Path) -> None:
    audio_dir = tmp_path / "audio" / "en"
    segments = [{"key": "Scene1_Intro", "text": "Hello world."}]
    signature = "sig-a"

    stats = prune_stale_audio(tmp_path, segments, signature)
    assert stats == {"reused": 0, "invalidated": 0}
    _seed_segment(audio_dir, "Scene1_Intro")

    stats = prune_stale_audio(tmp_path, segments, signature)
    assert stats == {"reused": 1, "invalidated": 0}
    assert (audio_dir / "Scene1_Intro.wav").exists()


def test_changed_text_invalidates_segment(tmp_path: Path) -> None:
    audio_dir = tmp_path / "audio" / "en"
    signature = "sig-a"
    prune_stale_audio(tmp_path, [{"key": "S1", "text": "old text"}], signature)
    _seed_segment(audio_dir, "S1")

    stats = prune_stale_audio(tmp_path, [{"key": "S1", "text": "new text"}], signature)
    assert stats == {"reused": 0, "invalidated": 1}
    assert not (audio_dir / "S1.wav").exists()
    assert not (audio_dir / "S1.mp3").exists()
    assert not (audio_dir / "S1.padded.wav").exists()


def test_changed_voice_signature_invalidates_all(tmp_path: Path) -> None:
    audio_dir = tmp_path / "audio" / "en"
    segments = [{"key": "S1", "text": "same"}, {"key": "S2", "text": "same too"}]
    prune_stale_audio(tmp_path, segments, "sig-a")
    _seed_segment(audio_dir, "S1")
    _seed_segment(audio_dir, "S2")

    stats = prune_stale_audio(tmp_path, segments, "sig-b")
    assert stats == {"reused": 0, "invalidated": 2}
    assert not (audio_dir / "S1.wav").exists()
    assert not (audio_dir / "S2.wav").exists()


def test_removed_segment_files_are_deleted(tmp_path: Path) -> None:
    audio_dir = tmp_path / "audio" / "en"
    signature = "sig-a"
    prune_stale_audio(
        tmp_path,
        [{"key": "Keep", "text": "kept"}, {"key": "Gone", "text": "removed"}],
        signature,
    )
    _seed_segment(audio_dir, "Keep")
    _seed_segment(audio_dir, "Gone")

    stats = prune_stale_audio(tmp_path, [{"key": "Keep", "text": "kept"}], signature)
    assert stats == {"reused": 1, "invalidated": 0}
    assert (audio_dir / "Keep.wav").exists()
    assert not (audio_dir / "Gone.wav").exists()


def test_partial_repair_only_invalidates_changed_scene(tmp_path: Path) -> None:
    audio_dir = tmp_path / "audio" / "en"
    signature = "sig-a"
    segments = [
        {"key": "S1", "text": "first narration"},
        {"key": "S2", "text": "second narration"},
        {"key": "S3", "text": "third narration"},
    ]
    prune_stale_audio(tmp_path, segments, signature)
    for segment in segments:
        _seed_segment(audio_dir, segment["key"])

    segments[1]["text"] = "second narration, repaired"
    stats = prune_stale_audio(tmp_path, segments, signature)
    assert stats == {"reused": 2, "invalidated": 1}
    assert (audio_dir / "S1.wav").exists()
    assert not (audio_dir / "S2.wav").exists()
    assert (audio_dir / "S3.wav").exists()


def test_voice_signature_changes_with_params(monkeypatch) -> None:
    monkeypatch.setenv("VIDEO_API_VOICE_ENGINE", "kokoro")
    monkeypatch.setenv("VIDEO_API_KOKORO_VOICE", "af_bella")
    sig_a = voice_signature(Settings())
    monkeypatch.setenv("VIDEO_API_KOKORO_VOICE", "ff_siwis")
    sig_b = voice_signature(Settings())
    assert sig_a != sig_b


def test_voice_signature_ignores_server_location_and_secrets() -> None:
    base = Settings(
        voice_engine="moss-remote",
        tts_server_url="http://gpu-a:8100",
        tts_server_api_key="key-1",
        tts_server_timeout_seconds=3600,
    )
    moved = Settings(
        voice_engine="moss-remote",
        tts_server_url="http://gpu-b:8100",
        tts_server_api_key="key-2",
        tts_server_timeout_seconds=900,
    )
    other_model = Settings(
        voice_engine="moss-remote",
        tts_server_url="http://gpu-a:8100",
        tts_server_api_key="key-1",
        moss_tts_model="other/model",
    )

    assert voice_signature(base) == voice_signature(moved)
    assert voice_signature(base) != voice_signature(other_model)


def test_segment_fingerprint_normalizes_whitespace() -> None:
    assert segment_fingerprint("a  b\nc", "s") == segment_fingerprint("a b c", "s")
    assert segment_fingerprint("a b", "s") != segment_fingerprint("a c", "s")
