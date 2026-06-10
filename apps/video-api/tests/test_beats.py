import json
from pathlib import Path
from types import SimpleNamespace

from video_api.pipeline.beats import CUE_MAX, CUE_MIN, find_anchor, resolve_cues


def _words(text: str, step: float = 0.5) -> list[dict]:
    return [
        {"w": w, "start": round(i * step, 3), "end": round(i * step + 0.4, 3)}
        for i, w in enumerate(text.split())
    ]


def test_find_anchor_exact_match() -> None:
    words = _words("the kernel talks to the hardware on your behalf")
    start = find_anchor(words, "talks to the hardware")
    assert start == 1.0  # word index 2 * 0.5s


def test_find_anchor_tolerates_small_drift() -> None:
    words = _words("a system call is the doorway into the kernel")
    # "the" dropped from the anchor — still close enough.
    start = find_anchor(words, "system call is doorway")
    assert start is not None
    assert start == 0.5


def test_find_anchor_rejects_unrelated_text() -> None:
    words = _words("completely different sentence about photosynthesis")
    assert find_anchor(words, "kernel page tables") is None


def test_find_anchor_normalizes_numbers() -> None:
    words = _words("a sixty four bit address space")
    start = find_anchor(words, "a 64-bit address")
    assert start is not None


def _scene(key: str, beats: list[str]) -> SimpleNamespace:
    return SimpleNamespace(key=key, beats=[SimpleNamespace(anchor=a) for a in beats])


def _setup_video_dir(tmp_path: Path, alignment: dict, durations: dict, scenes: list[dict]) -> None:
    audio_dir = tmp_path / "audio" / "en"
    audio_dir.mkdir(parents=True)
    (audio_dir / "alignment.json").write_text(json.dumps(alignment), encoding="utf-8")
    (audio_dir / "durations.json").write_text(json.dumps(durations), encoding="utf-8")
    (tmp_path / "scenes_map.json").write_text(
        json.dumps({"fps": 30, "scenes": scenes}), encoding="utf-8"
    )


def test_resolve_cues_injects_into_scenes_map(tmp_path: Path) -> None:
    narration = "first the request arrives then the kernel processes it and finally a response returns"
    _setup_video_dir(
        tmp_path,
        alignment={"S1": {"words": _words(narration)}},
        durations={"S1": 10.0},
        scenes=[{"key": "S1", "component": "FlowScene", "props": {"title": "T"}}],
    )
    blueprint = SimpleNamespace(
        scenes=[
            _scene(
                "S1",
                [
                    "first the request arrives",
                    "then the kernel processes",
                    "finally a response returns",
                ],
            )
        ]
    )

    cues_by_key = resolve_cues(tmp_path, blueprint)
    assert "S1" in cues_by_key
    cues = cues_by_key["S1"]
    assert len(cues) == 3
    assert all(c is not None for c in cues)
    assert cues == sorted(cues)  # ascending
    assert all(CUE_MIN <= c <= CUE_MAX for c in cues)

    scene_map = json.loads((tmp_path / "scenes_map.json").read_text(encoding="utf-8"))
    assert scene_map["scenes"][0]["props"]["cues"] == cues


def test_resolve_cues_unmatched_anchor_is_null(tmp_path: Path) -> None:
    narration = "the scheduler decides which task runs next"
    _setup_video_dir(
        tmp_path,
        alignment={"S1": {"words": _words(narration)}},
        durations={"S1": 8.0},
        scenes=[{"key": "S1", "component": "BulletScene", "props": {}}],
    )
    blueprint = SimpleNamespace(
        scenes=[_scene("S1", ["the scheduler decides", "totally absent anchor phrase"])]
    )

    cues = resolve_cues(tmp_path, blueprint)["S1"]
    assert cues[0] is not None
    assert cues[1] is None


def test_resolve_cues_forces_ascending_order(tmp_path: Path) -> None:
    # "the kernel" appears twice; the second anchor could match the early
    # occurrence and jump backwards — it must be pinned after the previous cue.
    narration = "the kernel boots first and later the kernel schedules tasks"
    _setup_video_dir(
        tmp_path,
        alignment={"S1": {"words": _words(narration)}},
        durations={"S1": 10.0},
        scenes=[{"key": "S1", "component": "BulletScene", "props": {}}],
    )
    blueprint = SimpleNamespace(
        scenes=[
            _scene(
                "S1",
                ["later the kernel schedules tasks", "the kernel boots first"],
            )
        ]
    )

    cues = resolve_cues(tmp_path, blueprint)["S1"]
    resolved = [c for c in cues if c is not None]
    assert resolved == sorted(resolved)


def test_resolve_cues_missing_alignment_is_noop(tmp_path: Path) -> None:
    audio_dir = tmp_path / "audio" / "en"
    audio_dir.mkdir(parents=True)
    blueprint = SimpleNamespace(scenes=[_scene("S1", ["whatever"])])
    assert resolve_cues(tmp_path, blueprint) == {}


def test_resolve_cues_scene_without_beats_is_skipped(tmp_path: Path) -> None:
    _setup_video_dir(
        tmp_path,
        alignment={"S1": {"words": _words("some words here")}},
        durations={"S1": 5.0},
        scenes=[{"key": "S1", "component": "TitleScene", "props": {}}],
    )
    blueprint = SimpleNamespace(scenes=[SimpleNamespace(key="S1", beats=[])])
    assert resolve_cues(tmp_path, blueprint) == {}
    scene_map = json.loads((tmp_path / "scenes_map.json").read_text(encoding="utf-8"))
    assert "cues" not in scene_map["scenes"][0]["props"]
