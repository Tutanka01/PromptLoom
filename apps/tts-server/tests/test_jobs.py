from __future__ import annotations

import wave
from pathlib import Path

from tts_server.cache import AudioCache
from tts_server.config import Settings
from tts_server.engine import FakeEngine
from tts_server.jobs import JobStore


def _write_wav(path: Path, frames: int = 2400) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(b"\x00\x00" * frames)
    return path.read_bytes()


def _store(tmp_path: Path) -> tuple[Settings, FakeEngine, AudioCache, JobStore]:
    settings = Settings(
        fake_engine=True,
        data_dir=tmp_path / "data",
        model_id="OpenMOSS-Team/MOSS-TTS-v1.5",
        image_digest=f"sha256:{'1' * 64}",
    )
    engine = FakeEngine(settings)
    engine._load_safely()
    cache = AudioCache(settings.cache_dir)
    return settings, engine, cache, JobStore(settings, engine, cache)


def _seed(
    tmp_path: Path,
    cache: AudioCache,
    settings: Settings,
    *,
    text: str,
    reference: Path | None,
    name: str,
    frames: int = 2400,
) -> bytes:
    source = tmp_path / f"{name}-source.wav"
    content = _write_wav(source, frames)
    seed_engine = FakeEngine(settings)
    seed_engine._load_safely()
    engine_profile = seed_engine.synthesis_profile()
    assert engine_profile is not None
    _, fingerprint = cache.identity(
        engine_profile=engine_profile,
        language="en",
        text=text,
        reference_hash=cache.file_hash(reference),
    )
    cache.store(fingerprint, source)
    return content


def test_explicit_reference_hits_complete_at_admission_without_fifo(tmp_path: Path) -> None:
    settings, engine, cache, jobs = _store(tmp_path)
    reference = tmp_path / "reference.wav"
    reference_bytes = _write_wav(reference, 1200)
    expected = {
        "Scene1": _seed(
            tmp_path,
            cache,
            settings,
            text="First.",
            reference=reference,
            name="first",
        ),
        "Scene2": _seed(
            tmp_path,
            cache,
            settings,
            text="Second.",
            reference=reference,
            name="second",
        ),
    }

    job = jobs.create(
        language="en",
        consistent_voice=True,
        segments=[("Scene1", "First."), ("Scene2", "Second.")],
        reference_bytes=reference_bytes,
    )

    assert job.status == "completed"
    assert job.finished_at is not None
    assert jobs.queue_depth() == 0
    assert all(segment.status == "done" and segment.cached for segment in job.segments)
    assert engine.calls == []
    for key, content in expected.items():
        assert (jobs.job_dir(job.id) / f"{key}.wav").read_bytes() == content
        assert not (jobs.job_dir(job.id) / f"{key}.wav.part").exists()


def test_admission_hit_bypasses_a_job_already_waiting_in_fifo(tmp_path: Path) -> None:
    settings, _engine, cache, jobs = _store(tmp_path)
    blocker = jobs.create(
        language="en",
        consistent_voice=False,
        segments=[("Blocker", "This is a cache miss.")],
        reference_bytes=None,
    )
    assert blocker.status == "queued"
    assert jobs.queue_depth() == 1

    reference = tmp_path / "reference.wav"
    reference_bytes = _write_wav(reference)
    _seed(
        tmp_path,
        cache,
        settings,
        text="Cached.",
        reference=reference,
        name="cached",
    )
    hit = jobs.create(
        language="en",
        consistent_voice=True,
        segments=[("Cached", "Cached.")],
        reference_bytes=reference_bytes,
    )

    assert hit.status == "completed"
    assert hit.segments[0].cached is True
    assert jobs.queue_depth() == 1


def test_partial_admission_hit_sends_only_miss_to_engine(tmp_path: Path) -> None:
    settings, engine, cache, jobs = _store(tmp_path)
    reference = tmp_path / "reference.wav"
    reference_bytes = _write_wav(reference)
    _seed(
        tmp_path,
        cache,
        settings,
        text="Cached.",
        reference=reference,
        name="cached",
    )

    job = jobs.create(
        language="en",
        consistent_voice=True,
        segments=[("Cached", "Cached."), ("Miss", "Generate me.")],
        reference_bytes=reference_bytes,
    )

    assert job.status == "queued"
    assert [segment.status for segment in job.segments] == ["done", "pending"]
    jobs._process(job)

    assert job.status == "completed"
    assert [call[0] for call in engine.calls] == ["Generate me."]


def test_implicit_reference_miss_keeps_first_segment_as_barrier(tmp_path: Path) -> None:
    settings, _engine, cache, jobs = _store(tmp_path)
    # A no-reference hit for the second segment must not be used: its real
    # fingerprint depends on the first segment's as-yet unknown WAV.
    _seed(
        tmp_path,
        cache,
        settings,
        text="Second.",
        reference=None,
        name="wrong-anchor",
    )

    job = jobs.create(
        language="en",
        consistent_voice=True,
        segments=[("Scene1", "First miss."), ("Scene2", "Second.")],
        reference_bytes=None,
    )

    assert job.status == "queued"
    assert [segment.status for segment in job.segments] == ["pending", "pending"]
    assert jobs.queue_depth() == 1


def test_implicit_reference_first_hit_unlocks_following_hits(tmp_path: Path) -> None:
    settings, engine, cache, jobs = _store(tmp_path)
    first_content = _seed(
        tmp_path,
        cache,
        settings,
        text="First.",
        reference=None,
        name="first-anchor",
        frames=1200,
    )
    anchor = tmp_path / "materialized-anchor.wav"
    anchor.write_bytes(first_content)
    _seed(
        tmp_path,
        cache,
        settings,
        text="Second.",
        reference=anchor,
        name="second",
    )

    job = jobs.create(
        language="en",
        consistent_voice=True,
        segments=[("Scene1", "First."), ("Scene2", "Second.")],
        reference_bytes=None,
    )

    assert job.status == "completed"
    assert all(segment.cached for segment in job.segments)
    assert jobs.queue_depth() == 0
    assert engine.calls == []


def test_non_consistent_job_preflights_all_no_reference_hits(tmp_path: Path) -> None:
    settings, _engine, cache, jobs = _store(tmp_path)
    for key, text in [("Scene1", "First."), ("Scene2", "Second.")]:
        _seed(
            tmp_path,
            cache,
            settings,
            text=text,
            reference=None,
            name=key,
        )

    job = jobs.create(
        language="en",
        consistent_voice=False,
        segments=[("Scene1", "First."), ("Scene2", "Second.")],
        reference_bytes=None,
    )

    assert job.status == "completed"
    assert all(segment.cached for segment in job.segments)
    assert jobs.queue_depth() == 0
