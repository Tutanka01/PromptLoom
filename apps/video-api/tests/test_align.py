import json
from pathlib import Path

from video_api.pipeline.align import align_segments, normalize_words, surface_tokens


def test_normalize_words_basic() -> None:
    assert normalize_words("The Kernel, talks to hardware!") == [
        "the", "kernel", "talks", "to", "hardware",
    ]


def test_surface_tokens_preserve_case_and_punctuation() -> None:
    # The surface keeps the real spoken word (case + punctuation) for display;
    # its sub-tokens are the normalized pieces fed to the aligner. Flattening the
    # sub-tokens must equal normalize_words so the same flat sequence still aligns.
    text = "The Kernel, talks to hardware!"
    tokens = surface_tokens(text)
    assert [surface for surface, _ in tokens] == [
        "The", "Kernel,", "talks", "to", "hardware!",
    ]
    flat = [sub for _, subs in tokens for sub in subs]
    assert flat == normalize_words(text)


def test_surface_tokens_digit_word_spawns_multiple_subtokens() -> None:
    tokens = surface_tokens("use 64-bit addressing")
    by_surface = {surface: subs for surface, subs in tokens}
    # The real "64-bit" stays intact for display, but aligns via spelled digits.
    assert "64-bit" in by_surface
    assert len(by_surface["64-bit"]) == 3  # sixty / four / bit
    assert by_surface["64-bit"][-1] == "bit"


def test_normalize_words_folds_diacritics_but_surface_keeps_accents() -> None:
    # Alignment charset is ASCII (CTC); accents must fold, NOT be dropped.
    assert normalize_words("été du système") == ["ete", "du", "systeme"]
    # ...while the surface (what the viewer reads) keeps the real accents.
    assert [surface for surface, _ in surface_tokens("été du système")] == [
        "été", "du", "système",
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


def test_align_segments_writes_surface_captions(tmp_path: Path) -> None:
    audio_dir = tmp_path / "audio" / "en"
    audio_dir.mkdir(parents=True)
    _write_segments(tmp_path, [{"key": "S1", "text": "The kernel, runs."}])
    (audio_dir / "S1.wav").write_bytes(b"RIFF")

    alignment = align_segments(tmp_path, aligner=_fake_aligner)
    captions = alignment["S1"]["captions"]
    # Real surface text with case + punctuation, NOT the normalized form.
    assert [c["text"] for c in captions] == ["The", "kernel,", "runs."]
    # Timing carried straight from the aligned sub-token (1:1 here).
    assert captions[0]["start"] == 0.0
    assert captions[1]["start"] == 0.5


def test_align_segments_caption_spans_digit_expansion(tmp_path: Path) -> None:
    audio_dir = tmp_path / "audio" / "en"
    audio_dir.mkdir(parents=True)
    _write_segments(tmp_path, [{"key": "S1", "text": "use 64-bit"}])
    (audio_dir / "S1.wav").write_bytes(b"RIFF")

    alignment = align_segments(tmp_path, aligner=_fake_aligner)
    captions = alignment["S1"]["captions"]
    assert [c["text"] for c in captions] == ["use", "64-bit"]
    # "64-bit" aligns via three sub-tokens (sixty/four/bit): its display span
    # runs from the first sub-token's start to the last sub-token's end.
    assert captions[1]["start"] == 0.5   # "sixty"
    assert captions[1]["end"] == 1.9     # end of "bit" (index 3 -> 1.5 + 0.4)


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
