import json
from pathlib import Path

from video_api.pipeline.captions import build_cues, write_subtitles


def _toks(words: list[str], step: float = 0.5, dur: float = 0.4) -> list[dict]:
    """Surface caption tokens, one per word, evenly spaced."""
    return [
        {"text": w, "start": round(i * step, 3), "end": round(i * step + dur, 3)}
        for i, w in enumerate(words)
    ]


def _lines(cue: dict) -> str:
    return "\n".join(" ".join(w["text"] for w in line) for line in cue["lines"])


def test_build_cues_breaks_on_sentence_punctuation() -> None:
    cues = build_cues(_toks(["The", "kernel", "runs.", "It", "is", "fast."]))
    assert [_lines(c) for c in cues] == ["The kernel runs.", "It is fast."]


def test_build_cues_does_not_split_tiny_fragment_off() -> None:
    # "I/O." alone is too short to be its own flashing cue; it stays attached.
    cues = build_cues(_toks(["I/O.", "The", "disk", "is", "slow."]))
    assert len(cues) == 1
    assert _lines(cues[0]) == "I/O. The disk is slow."


def test_build_cues_wraps_within_max_lines_and_width() -> None:
    words = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel"]
    cues = build_cues(_toks(words), max_line=18, max_lines=2)
    # Every cue fits the budget; no line exceeds the width, no cue over 2 lines.
    for cue in cues:
        assert len(cue["lines"]) <= 2
        for line in cue["lines"]:
            assert len(" ".join(w["text"] for w in line)) <= 18
    # All words preserved, in order, across the cues.
    flat = [w["text"] for cue in cues for line in cue["lines"] for w in line]
    assert flat == words


def test_build_cues_balances_two_line_wrap() -> None:
    # A sentence that must wrap should split into two balanced lines, not leave a
    # single orphan word on line two (a hallmark of amateur subtitles).
    words = "Le noyau gère la mémoire de chaque processus.".split()
    cues = build_cues(_toks(words), max_line=42)
    assert len(cues) == 1
    lines = cues[0]["lines"]
    assert len(lines) == 2
    assert len(lines[1]) >= 2  # line two is not a lone orphan
    l1 = " ".join(w["text"] for w in lines[0])
    l2 = " ".join(w["text"] for w in lines[1])
    assert abs(len(l1) - len(l2)) <= 6


def test_build_cues_caps_cue_duration() -> None:
    cues = build_cues(_toks(["one", "two", "three", "four", "five", "six"]), max_dur=2.0)
    assert len(cues) >= 2
    for cue in cues:
        assert cue["end"] - cue["start"] <= 2.0 + 1e-6


def test_build_cues_preserves_word_timing() -> None:
    cues = build_cues(_toks(["hello", "world."]))
    first = cues[0]["lines"][0][0]
    assert first == {"text": "hello", "start": 0.0, "end": 0.4}


def test_build_cues_extends_short_cue_to_min_duration() -> None:
    cues = build_cues([{"text": "Yes.", "start": 0.0, "end": 0.3}], min_dur=0.8)
    assert cues[0]["end"] == 0.8


def _setup(video_dir: Path, alignment: dict, durations: dict, scenes_map: dict) -> None:
    audio = video_dir / "audio" / "en"
    audio.mkdir(parents=True)
    (audio / "alignment.json").write_text(json.dumps(alignment), encoding="utf-8")
    (audio / "durations.json").write_text(json.dumps(durations), encoding="utf-8")
    (video_dir / "scenes_map.json").write_text(json.dumps(scenes_map), encoding="utf-8")


def test_write_subtitles_writes_global_continuous_cues(tmp_path: Path) -> None:
    _setup(
        tmp_path,
        alignment={
            "S1": {"captions": [{"text": "Hello.", "start": 0.0, "end": 0.5}]},
            "S2": {"captions": [{"text": "World.", "start": 0.0, "end": 0.5}]},
        },
        durations={"S1": 2.0, "S2": 2.0},
        scenes_map={
            "fps": 30,
            "scenes": [
                {"key": "S1", "component": "A", "props": {}},
                {"key": "S2", "component": "B", "props": {}},
            ],
        },
    )
    write_subtitles(tmp_path, slug="demo", language="en")
    # The burned-in track reads ONE global, whole-video cue list (not per-scene),
    # so it can render continuously regardless of scene/beat boundaries.
    cues = json.loads((tmp_path / "subtitles.json").read_text())["cues"]
    assert cues[0]["start"] == 0.0
    assert cues[1]["start"] == 2.0  # S2 offset by S1's 2.0s of audio
    # Word timings inside the cue are global too, so karaoke stays in sync.
    assert cues[1]["lines"][0][0]["start"] == 2.0


def test_write_subtitles_srt_uses_global_offsets(tmp_path: Path) -> None:
    _setup(
        tmp_path,
        alignment={
            "S1": {"captions": [{"text": "Hello.", "start": 0.0, "end": 0.5}]},
            "S2": {"captions": [{"text": "World.", "start": 0.0, "end": 0.5}]},
        },
        durations={"S1": 2.0, "S2": 2.0},
        scenes_map={
            "fps": 30,
            "scenes": [
                {"key": "S1", "component": "A", "props": {}},
                {"key": "S2", "component": "B", "props": {}},
            ],
        },
    )
    write_subtitles(tmp_path, slug="demo", language="en")
    srt = (tmp_path / "final" / "demo-en.srt").read_text(encoding="utf-8")
    assert "Hello." in srt and "World." in srt
    # S2 starts after S1's 2.0s of audio -> 00:00:02,000 on the global timeline.
    assert "00:00:02,000 -->" in srt
    vtt = (tmp_path / "final" / "demo-en.vtt").read_text(encoding="utf-8")
    assert vtt.startswith("WEBVTT")
    assert "00:00:02.000 -->" in vtt
