import json
from pathlib import Path

from video_api.pipeline.align import align_segments, normalize_words


def test_normalize_words_basic() -> None:
    assert normalize_words("The Kernel, talks to hardware!") == [
        "the", "kernel", "talks", "to", "hardware",
    ]


def test_normalize_words_spells_digits() -> None:
    words = normalize_words("a 64-bit address")
    assert words[0] == "a"
    assert "bit" in words and "address" in words
    # "64" must be spelled out, never kept as digits.
    assert all(not w.isdigit() for w in words)
    assert "sixty" in words or "six" in words


def test_normalize_words_handles_apostrophes_and_empty() -> None:
    assert normalize_words("it's the CPU's job") == ["it's", "the", "cpu's", "job"]
    assert normalize_words("   ") == []


def _write_segments(video_dir: Path, segments: list[dict]) -> None:
    (video_dir / "segments_en.json").write_text(
        json.dumps({"segments": segments}), encoding="utf-8"
    )


def _fake_aligner(wav_path: Path, words: list[str]):
    # 0.5s per word, deterministic.
    return [(i * 0.5, i * 0.5 + 0.4) for i in range(len(words))]


def test_align_segments_writes_alignment(tmp_path: Path) -> None:
    audio_dir = tmp_path / "audio" / "en"
    audio_dir.mkdir(parents=True)
    _write_segments(tmp_path, [{"key": "S1", "text": "hello brave new world"}])
    (audio_dir / "S1.wav").write_bytes(b"RIFF")

    alignment = align_segments(tmp_path, aligner=_fake_aligner)
    assert "S1" in alignment
    words = alignment["S1"]["words"]
    assert [w["w"] for w in words] == ["hello", "brave", "new", "world"]
    assert words[1]["start"] == 0.5
    on_disk = json.loads((audio_dir / "alignment.json").read_text(encoding="utf-8"))
    assert on_disk["S1"]["words"] == words


def test_align_segments_skips_missing_wav(tmp_path: Path) -> None:
    audio_dir = tmp_path / "audio" / "en"
    audio_dir.mkdir(parents=True)
    _write_segments(
        tmp_path,
        [
            {"key": "S1", "text": "has audio"},
            {"key": "S2", "text": "no audio"},
        ],
    )
    (audio_dir / "S1.wav").write_bytes(b"RIFF")

    alignment = align_segments(tmp_path, aligner=_fake_aligner)
    assert set(alignment) == {"S1"}


def test_align_segments_reuses_cached_entry_by_fingerprint(tmp_path: Path) -> None:
    audio_dir = tmp_path / "audio" / "en"
    audio_dir.mkdir(parents=True)
    _write_segments(tmp_path, [{"key": "S1", "text": "stable narration here"}])
    (audio_dir / "S1.wav").write_bytes(b"RIFF")
    (audio_dir / "cache.json").write_text(json.dumps({"S1": "fp-1"}), encoding="utf-8")

    calls: list[str] = []

    def counting_aligner(wav_path: Path, words: list[str]):
        calls.append(wav_path.name)
        return _fake_aligner(wav_path, words)

    align_segments(tmp_path, aligner=counting_aligner)
    assert calls == ["S1.wav"]

    # Same fingerprint -> cached words reused, aligner not called again.
    align_segments(tmp_path, aligner=counting_aligner)
    assert calls == ["S1.wav"]

    # Changed fingerprint (audio regenerated) -> realigned.
    (audio_dir / "cache.json").write_text(json.dumps({"S1": "fp-2"}), encoding="utf-8")
    align_segments(tmp_path, aligner=counting_aligner)
    assert calls == ["S1.wav", "S1.wav"]


def test_align_segments_failure_is_per_segment(tmp_path: Path) -> None:
    audio_dir = tmp_path / "audio" / "en"
    audio_dir.mkdir(parents=True)
    _write_segments(
        tmp_path,
        [
            {"key": "Bad", "text": "this one explodes"},
            {"key": "Good", "text": "this one aligns"},
        ],
    )
    (audio_dir / "Bad.wav").write_bytes(b"RIFF")
    (audio_dir / "Good.wav").write_bytes(b"RIFF")

    def flaky_aligner(wav_path: Path, words: list[str]):
        if wav_path.stem == "Bad":
            raise RuntimeError("boom")
        return _fake_aligner(wav_path, words)

    alignment = align_segments(tmp_path, aligner=flaky_aligner)
    assert set(alignment) == {"Good"}
