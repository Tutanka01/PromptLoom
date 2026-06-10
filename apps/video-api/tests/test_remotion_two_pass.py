import re
from pathlib import Path

from video_api.pipeline.llm import _rescale_outline_durations, _safe_int
from video_api.pipeline.remotion_blueprint import (
    ICON_NAMES,
    normalize_remotion_blueprint,
    validate_scene_payload,
)

REMOTION_DIR = Path(__file__).resolve().parents[3] / "apps" / "video-api" / "remotion"


NARRATION = (
    "A system call is the doorway into the kernel. When a program needs to read a file, "
    "it cannot touch the disk directly. Instead it asks the kernel, which checks permissions "
    "and performs the read on the program's behalf before returning the data."
)


def _scene(component: str, props: dict, beats: list | None = None) -> dict:
    return {
        "key": "Scene2_CoreEN",
        "title": "Core idea",
        "component": component,
        "narration": NARRATION,
        "props": props,
        "beats": beats or [],
    }


def test_validate_rejects_empty_list_props() -> None:
    errors = validate_scene_payload(_scene("BulletScene", {"bullets": []}))
    assert any("bullets" in e for e in errors)


def test_validate_rejects_placeholder_code() -> None:
    errors = validate_scene_payload(_scene("CodeScene", {"code": "# code"}))
    assert any("code" in e for e in errors)


def test_validate_rejects_placeholder_command() -> None:
    errors = validate_scene_payload(_scene("TerminalScene", {"command": "echo hello"}))
    assert any("command" in e for e in errors)


def test_validate_rejects_plot_without_expr_or_points() -> None:
    errors = validate_scene_payload(_scene("PlotScene", {"xRange": [-4, 4]}))
    assert any("expr" in e for e in errors)


def test_validate_rejects_anchor_not_in_narration() -> None:
    errors = validate_scene_payload(
        _scene(
            "BulletScene",
            {"bullets": ["doorway into the kernel", "checks permissions"]},
            beats=[{"anchor": "doorway into the kernel"}, {"anchor": "photosynthesis in plants"}],
        )
    )
    assert any("photosynthesis" in e for e in errors)


def test_validate_rejects_anchor_count_drift() -> None:
    errors = validate_scene_payload(
        _scene(
            "BulletScene",
            {"bullets": ["a", "b", "c", "d"]},
            beats=[{"anchor": "doorway into the kernel"}],
        )
    )
    assert any("anchors" in e for e in errors)


def test_validate_requires_beats_on_multi_item_scene() -> None:
    errors = validate_scene_payload(
        _scene("BulletScene", {"bullets": ["doorway", "permissions", "returns data"]})
    )
    assert any("without beats" in e for e in errors)


def test_validate_accepts_complete_scene() -> None:
    errors = validate_scene_payload(
        _scene(
            "BulletScene",
            {"bullets": ["the doorway", "checks permissions", "returns the data"]},
            beats=[
                {"anchor": "doorway into the kernel"},
                {"anchor": "checks permissions"},
                {"anchor": "returning the data"},
            ],
        )
    )
    assert errors == []


def test_normalize_records_degradations_for_placeholders() -> None:
    data = {
        "title": "T",
        "scenes": [
            {
                "key": "Scene1_AEN",
                "title": "A",
                "narration": NARRATION,
                "component": "FormulaScene",
                "props": {},
            },
            {
                "key": "Scene2_BEN",
                "title": "B",
                "narration": NARRATION,
                "component": "TerminalScene",
                "props": {"command": "strace -e trace=read cat notes.txt"},
            },
        ],
    }
    coerced = normalize_remotion_blueprint(data, 240)
    degradations = coerced["degradations"]
    assert any("FormulaScene" in d for d in degradations)
    # The terminal scene had a real command: no degradation recorded for it.
    assert not any("Scene2_BEN" in d for d in degradations)


def test_rescale_outline_durations_into_window() -> None:
    scenes = [{"duration_seconds": 10} for _ in range(8)]  # 80s for a 240s target
    for sc in scenes:
        sc["duration_seconds"] = max(12, min(90, sc["duration_seconds"]))
    _rescale_outline_durations(scenes, 240)
    planned = sum(sc["duration_seconds"] for sc in scenes)
    assert 180 <= planned <= 300


def test_rescale_outline_durations_noop_when_in_window() -> None:
    scenes = [{"duration_seconds": 30} for _ in range(8)]  # 240s for 240s target
    _rescale_outline_durations(scenes, 240)
    assert all(sc["duration_seconds"] == 30 for sc in scenes)


def test_safe_int() -> None:
    assert _safe_int("42", 0) == 42
    assert _safe_int(31.7, 0) == 31
    assert _safe_int("nope", 7) == 7
    assert _safe_int(None, 7) == 7


def test_icon_allowlist_matches_tsx() -> None:
    """The Python mirror must equal the keys of ICONS in catalog/Icon.tsx —
    otherwise the prompt advertises icons the renderer silently drops."""
    source = (REMOTION_DIR / "src" / "catalog" / "Icon.tsx").read_text(encoding="utf-8")
    body = source.split("const ICONS", 1)[1].split("};", 1)[0]
    tsx_names = set(re.findall(r'^\s+"?([a-z][a-z-]*)"?:', body, re.MULTILINE))
    assert tsx_names == set(ICON_NAMES)


def test_unknown_icons_are_dropped() -> None:
    data = {
        "title": "T",
        "scenes": [
            {
                "key": "Scene1_AEN",
                "title": "A",
                "narration": NARRATION,
                "component": "BulletScene",
                "props": {
                    "bullets": ["one", "two"],
                    "icons": ["cpu", "definitely-not-an-icon"],
                },
            }
        ],
    }
    coerced = normalize_remotion_blueprint(data, 240)
    assert coerced["scenes"][0]["props"]["icons"] == ["cpu", None]


def test_transition_normalized() -> None:
    data = {
        "title": "T",
        "scenes": [
            {
                "key": "Scene1_AEN",
                "title": "A",
                "narration": NARRATION,
                "component": "BulletScene",
                "props": {"bullets": ["one", "two"]},
                "transition": "Slide-Left",
            },
            {
                "key": "Scene2_BEN",
                "title": "B",
                "narration": NARRATION,
                "component": "BulletScene",
                "props": {"bullets": ["one", "two"]},
                "transition": "spin-3d",
            },
        ],
    }
    coerced = normalize_remotion_blueprint(data, 240)
    assert coerced["scenes"][0]["transition"] == "slide-left"
    assert coerced["scenes"][1]["transition"] == "auto"


def test_density_cap_rejected() -> None:
    errors = validate_scene_payload(
        _scene("BulletScene", {"bullets": [f"item {i}" for i in range(9)]})
    )
    assert any("too dense" in e for e in errors)
