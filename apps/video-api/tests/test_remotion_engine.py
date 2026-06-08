from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from video_api.config import Settings
from video_api.pipeline.engine import ManimEngine, RemotionEngine, make_engine
from video_api.pipeline.llm import LLMClient
from video_api.pipeline.remotion_blueprint import (
    fake_remotion_blueprint,
    normalize_remotion_blueprint,
    sample_expr,
)
from video_api.pipeline.remotion_materialize import (
    RemotionMaterializer,
    fallback_custom_to_palette,
    validate_remotion_video_source,
)
from video_api.pipeline.remotion_scene_coder import _validate_static
from video_api.schemas import RemotionBlueprint

REPO_ROOT = Path(__file__).resolve().parents[3]
REMOTION_DIR = REPO_ROOT / "apps" / "video-api" / "remotion"

# Symbols the scene-coder prompt (remotion_scene_coder._SYSTEM) advertises as
# importable "from ../../lib". The barrel MUST re-export every one of them, or a
# Custom scene that follows the prompt fails `tsc` and silently falls back to a
# BulletScene — which is exactly the bug this guards against.
_PROMISED_LIB_EXPORTS = [
    "AbsoluteFill", "tailFade", "colors", "mx", "my",
    "AmbientBackground", "MathFormula", "CodeBlock", "Plot",
    "TitleBar", "Card", "Arrow", "Caption", "TextReveal", "BlurReveal",
    "MemoryGrid", "FlowToken", "BarChart", "Counter", "Zone", "Terminal",
    "KernelBadge", "HardwareBox",
]


def _settings() -> Settings:
    return Settings(repo_root=REPO_ROOT, fake_llm=True)


# --------------------------------------------------------------------------- #
# Schema + fake blueprint
# --------------------------------------------------------------------------- #
def test_fake_remotion_blueprint_validates_and_passes_gates() -> None:
    bp = fake_remotion_blueprint("Explain the derivative", "math", 240)
    assert len(bp.scenes) >= 8
    assert bp.scenes[0].component == "TitleScene"
    assert bp.scenes[-1].component == "BulletScene"
    # keys ordered Scene1_..., Scene2_..., unique
    assert [s.key.split("_")[0] for s in bp.scenes] == [f"Scene{i}" for i in range(1, len(bp.scenes) + 1)]


def test_remotion_scene_text_alias() -> None:
    bp = fake_remotion_blueprint("x", "cs", 240)
    assert bp.scenes[0].text == bp.scenes[0].narration


def test_remotion_blueprint_rejects_short_narration() -> None:
    bp = fake_remotion_blueprint("x", "cs", 240).model_dump()
    for scene in bp["scenes"]:
        scene["narration"] = "Too short."
    with pytest.raises(Exception):
        RemotionBlueprint.model_validate(bp)


# --------------------------------------------------------------------------- #
# Normalisation
# --------------------------------------------------------------------------- #
def test_sample_expr_handles_bad_input() -> None:
    pts = sample_expr("sin(x)", -3.14, 3.14, n=10)
    assert len(pts) == 11
    assert all(len(p) == 2 for p in pts)
    # a broken expression degrades to zeros, never raises
    assert sample_expr("does_not_exist(x)", 0, 1, n=2) == [[0.0, 0.0], [0.5, 0.0], [1.0, 0.0]]


def test_normalise_expr_to_points_and_drops_expr() -> None:
    raw = {
        "title": "T", "theme": "math", "slug": "t", "target_duration_seconds": 240,
        "audience": "learners here", "teaching_goal": "goal goal goal goal",
        "style_notes": "dark clean style notes here",
        "scenes": [{
            "key": "Scene1_x", "title": "Hook", "narration": "word " * 60, "duration_seconds": 30,
            "component": "plot", "props": {"expr": "0.18*x**2", "xRange": [-4, 4], "yRange": [-1, 5]},
        }],
    }
    out = normalize_remotion_blueprint(raw, 240)
    s0 = out["scenes"][0]
    assert s0["component"] == "PlotScene"  # alias coerced
    assert "points" in s0["props"] and "expr" not in s0["props"]
    assert s0["key"] == "Scene1_xEN"


def _wrap_scene(component: str, props: dict, narration: str = None) -> dict:
    return {
        "title": "T", "theme": "cs", "slug": "t", "target_duration_seconds": 240,
        "audience": "learners here", "teaching_goal": "goal goal goal goal",
        "style_notes": "dark clean style notes here",
        "scenes": [{
            "key": "Scene1_x", "title": "Hook",
            "narration": narration or ("Sentence one here. Sentence two here. Sentence three here. " * 4),
            "duration_seconds": 30, "component": component, "props": props,
        }],
    }


def test_normalise_comparison_scene() -> None:
    out = normalize_remotion_blueprint(
        _wrap_scene("comparison", {"left": {"label": "User", "items": ["a", "b"]}, "right": ["x", "y"]}), 240
    )
    s0 = out["scenes"][0]
    assert s0["component"] == "ComparisonScene"  # alias coerced
    assert s0["props"]["left"] == {"label": "User", "items": ["a", "b"]}
    assert s0["props"]["right"]["label"] == "B" and s0["props"]["right"]["items"] == ["x", "y"]


def test_normalise_layered_and_timeline_records() -> None:
    layered = normalize_remotion_blueprint(
        _wrap_scene("layers", {"layers": ["Application", {"label": "Kernel", "sub": "ring 0"}, {"name": "Hardware"}]}), 240
    )["scenes"][0]
    assert layered["component"] == "LayeredSystemScene"
    assert layered["props"]["layers"] == [
        {"label": "Application"}, {"label": "Kernel", "sub": "ring 0"}, {"label": "Hardware"}
    ]
    timeline = normalize_remotion_blueprint(
        _wrap_scene("timeline", {"steps": [{"title": "BIOS"}, "Boot"]}), 240
    )["scenes"][0]
    assert timeline["component"] == "TimelineScene"
    assert timeline["props"]["steps"] == [{"label": "BIOS"}, {"label": "Boot"}]


def test_normalise_terminal_and_empty_fallbacks() -> None:
    term = normalize_remotion_blueprint(_wrap_scene("shell", {"cmd": "ls -la", "output": "a\nb"}), 240)["scenes"][0]
    assert term["component"] == "TerminalScene"
    assert term["props"]["command"] == "ls -la" and term["props"]["output"] == "a\nb"
    # garbage/empty props must still yield renderable, non-empty structure
    empty = normalize_remotion_blueprint(_wrap_scene("comparison", {}), 240)["scenes"][0]
    assert empty["props"]["left"]["items"] and empty["props"]["right"]["items"]
    bad_layers = normalize_remotion_blueprint(_wrap_scene("layers", {"layers": "nonsense"}), 240)["scenes"][0]
    assert bad_layers["props"]["layers"]  # fell back to narration-derived layers


def test_normalise_memory_flow_bar_counter() -> None:
    mem = normalize_remotion_blueprint(
        _wrap_scene("memory", {"cells": [{"label": "0x00", "highlight": True}, "0x08", {"label": "0x10", "sub": "PTE"}], "cols": 9}), 240
    )["scenes"][0]
    assert mem["component"] == "MemoryScene"
    assert mem["props"]["cells"][0] == {"label": "0x00", "highlight": True}
    assert mem["props"]["cells"][1] == {"label": "0x08"}
    assert mem["props"]["cols"] == 6  # clamped 1..6

    flow = normalize_remotion_blueprint(_wrap_scene("packet", {"stages": [{"label": "lib"}, "trap", {"name": "kernel"}]}), 240)["scenes"][0]
    assert flow["component"] == "FlowScene"
    assert flow["props"]["stages"] == [{"label": "lib"}, {"label": "trap"}, {"label": "kernel"}]

    bar = normalize_remotion_blueprint(_wrap_scene("bars", {"bars": [{"label": "read", "value": "12"}, {"label": "write", "value": 8}]}), 240)["scenes"][0]
    assert bar["component"] == "BarChartScene"
    assert bar["props"]["bars"] == [{"label": "read", "value": 12.0}, {"label": "write", "value": 8.0}]

    cnt = normalize_remotion_blueprint(_wrap_scene("metric", {"value": "1000000", "suffix": "/s", "label": "syscalls"}), 240)["scenes"][0]
    assert cnt["component"] == "CounterScene"
    assert cnt["props"]["value"] == 1000000.0 and cnt["props"]["suffix"] == "/s"


def test_normalise_new_scenes_empty_fallbacks() -> None:
    # garbage/empty props must still yield renderable structure (never crash render)
    mem = normalize_remotion_blueprint(_wrap_scene("memory", {"cells": "nope"}), 240)["scenes"][0]
    assert mem["props"]["cells"]  # fell back to address cells
    bar = normalize_remotion_blueprint(_wrap_scene("bars", {}), 240)["scenes"][0]
    assert bar["props"]["bars"] and all("value" in b for b in bar["props"]["bars"])
    cnt = normalize_remotion_blueprint(_wrap_scene("counter", {}), 240)["scenes"][0]
    assert isinstance(cnt["props"]["value"], float)


def test_normalise_narration_field_aliases() -> None:
    raw = {
        "title": "T", "slug": "t", "scenes": [
            {"key": "Scene1_a", "title": "A", "text": "spoken via text field", "component": "bullet"}
        ],
    }
    out = normalize_remotion_blueprint(raw, 240)
    assert out["scenes"][0]["narration"] == "spoken via text field"
    assert out["scenes"][0]["component"] == "BulletScene"


# --------------------------------------------------------------------------- #
# Materializer + build_video_json
# --------------------------------------------------------------------------- #
def test_materialize_writes_contract(tmp_path) -> None:
    bp = fake_remotion_blueprint("Explain page tables", "cs", 240)
    video_dir = RemotionMaterializer(_settings()).materialize(bp, tmp_path)
    for name in ["segments_en.json", "scenes_map.json", "build_video_json.py", "render_en.sh", "assemble_en.sh", "generate_voice_en.py"]:
        assert (video_dir / name).exists(), name
    validate_remotion_video_source(video_dir)
    # render script targets the silent mp4 + uses remotion render
    render = (video_dir / "render_en.sh").read_text()
    assert "remotion render" in render
    assert f"final/{bp.slug}-en-silent.mp4" in render


def test_segments_and_scenes_map_key_parity(tmp_path) -> None:
    bp = fake_remotion_blueprint("x", "cs", 240)
    video_dir = RemotionMaterializer(_settings()).materialize(bp, tmp_path)
    seg = {s["key"] for s in json.loads((video_dir / "segments_en.json").read_text())["segments"]}
    smap = {s["key"] for s in json.loads((video_dir / "scenes_map.json").read_text())["scenes"]}
    assert seg == smap == {s.key for s in bp.scenes}


def test_build_video_json_frames_from_durations(tmp_path) -> None:
    bp = fake_remotion_blueprint("x", "cs", 240)
    video_dir = RemotionMaterializer(_settings()).materialize(bp, tmp_path)
    smap = json.loads((video_dir / "scenes_map.json").read_text())
    (video_dir / "audio" / "en").mkdir(parents=True, exist_ok=True)
    (video_dir / "audio" / "en" / "durations.json").write_text(
        json.dumps({s["key"]: 3.0 for s in smap["scenes"]})
    )
    subprocess.run([sys.executable, "build_video_json.py"], cwd=video_dir, check=True, capture_output=True)
    video = json.loads((video_dir / "video.json").read_text())
    assert video["embedAudio"] is False
    assert len(video["scenes"]) == len(bp.scenes)
    assert video["scenes"][0]["durationInFrames"] == 180  # 3.0s * 60fps


def test_build_video_json_floors_missing_duration(tmp_path) -> None:
    bp = fake_remotion_blueprint("x", "cs", 240)
    video_dir = RemotionMaterializer(_settings()).materialize(bp, tmp_path)
    (video_dir / "audio" / "en").mkdir(parents=True, exist_ok=True)
    (video_dir / "audio" / "en" / "durations.json").write_text("{}")  # no durations
    subprocess.run([sys.executable, "build_video_json.py"], cwd=video_dir, check=True, capture_output=True)
    video = json.loads((video_dir / "video.json").read_text())
    assert all(s["durationInFrames"] >= 60 for s in video["scenes"])  # MIN_FRAMES


# --------------------------------------------------------------------------- #
# Custom -> palette fallback
# --------------------------------------------------------------------------- #
def test_fallback_custom_to_palette(tmp_path) -> None:
    bp = fake_remotion_blueprint("x", "cs", 240).model_dump()
    bp["scenes"][2]["component"] = "Custom"
    bp["scenes"][2]["visual_intent"] = "draw a page table mapping"
    blueprint = RemotionBlueprint.model_validate(bp)
    custom_key = blueprint.scenes[2].key
    assert blueprint.scenes[2].is_custom

    video_dir = RemotionMaterializer(_settings()).materialize(blueprint, tmp_path)
    fallback_custom_to_palette(video_dir, blueprint, {custom_key})
    smap = json.loads((video_dir / "scenes_map.json").read_text())
    entry = next(s for s in smap["scenes"] if s["key"] == custom_key)
    assert entry["component"] == "BulletScene"
    assert entry["custom"] is False
    assert entry["props"]["bullets"]


# --------------------------------------------------------------------------- #
# Scene-coder static guards
# --------------------------------------------------------------------------- #
def test_scene_coder_accepts_valid_component() -> None:
    # NOTE: this only exercises the string-level allow-list. Whether the imported
    # symbols actually resolve is covered by `test_lib_barrel_*` +
    # `test_remotion_project_typechecks` (the previously-missing guard that let
    # the dead `../../lib` barrel ship unnoticed).
    code = (
        'import React from "react";\n'
        'import { useCurrentFrame } from "remotion";\n'
        'import { AbsoluteFill, colors, tailFade } from "../../lib";\n'
        'export const Scene3_LimitEN: React.FC<any> = ({ dur }) => {\n'
        '  const f = useCurrentFrame();\n'
        '  return <AbsoluteFill style={{ opacity: tailFade(f / dur) }} />;\n'
        '};\n'
    )
    _validate_static(code, "Scene3_LimitEN")  # should not raise


@pytest.mark.parametrize(
    "snippet, key",
    [
        ('export const Scene1_xEN: React.FC<any> = () => { fetch("/x"); return null; };', "Scene1_xEN"),
        ('export const Scene1_xEN: React.FC<any> = () => { eval("1"); return null; };', "Scene1_xEN"),
        ('import fs from "fs";\nexport const Scene1_xEN: React.FC<any> = () => null;', "Scene1_xEN"),
        ('import x from "./secret";\nexport const Scene1_xEN: React.FC<any> = () => null;', "Scene1_xEN"),
    ],
)
def test_scene_coder_rejects_forbidden(snippet: str, key: str) -> None:
    with pytest.raises(ValueError):
        _validate_static(snippet, key)


def test_scene_coder_requires_exact_export_name() -> None:
    code = 'export const WrongName: React.FC<any> = () => null;'
    with pytest.raises(ValueError):
        _validate_static(code, "Scene1_xEN")


# --------------------------------------------------------------------------- #
# Custom-scene import surface: the `../../lib` barrel
# --------------------------------------------------------------------------- #
def test_lib_barrel_exists() -> None:
    assert (REMOTION_DIR / "src" / "lib.ts").exists(), (
        "remotion/src/lib.ts is the ONLY import surface Custom scenes may use; "
        "without it every Custom scene fails tsc and falls back to BulletScene"
    )


def test_lib_barrel_exports_promised_symbols() -> None:
    import re

    text = (REMOTION_DIR / "src" / "lib.ts").read_text(encoding="utf-8")
    exported: set[str] = set()
    for block in re.findall(r"export\s*(?:type\s*)?\{([^}]*)\}", text):
        for raw in block.split(","):
            name = raw.strip().split(" as ")[0].strip()
            if name:
                exported.add(name)
    missing = [s for s in _PROMISED_LIB_EXPORTS if s not in exported]
    assert not missing, f"lib.ts barrel is missing promised exports: {missing}"


def test_remotion_project_typechecks() -> None:
    """`tsc --noEmit` over the whole Remotion project: proves lib.ts compiles and
    every palette/catalog/scene file is type-correct. Auto-skips when the Node
    toolchain isn't present (local Python-only runs); always runs in the Docker
    `test` image, which installs node + node_modules."""
    import shutil

    if shutil.which("npx") is None or not (REMOTION_DIR / "node_modules").exists():
        pytest.skip("Node toolchain / node_modules not available")
    result = subprocess.run(
        ["npx", "--no-install", "tsc", "--noEmit"],
        cwd=REMOTION_DIR,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# --------------------------------------------------------------------------- #
# Engine selection
# --------------------------------------------------------------------------- #
def test_make_engine_selects_remotion() -> None:
    settings = Settings(repo_root=REPO_ROOT, render_engine="remotion", fake_llm=True)
    engine = make_engine(settings, LLMClient(settings))
    assert isinstance(engine, RemotionEngine)
    assert engine.name == "remotion"


def test_make_engine_defaults_to_manim() -> None:
    settings = Settings(repo_root=REPO_ROOT, render_engine="manim")
    engine = make_engine(settings, LLMClient(settings))
    assert isinstance(engine, ManimEngine)


def test_make_engine_unknown_falls_back_to_manim() -> None:
    settings = Settings(repo_root=REPO_ROOT, render_engine="bogus")
    assert isinstance(make_engine(settings, LLMClient(settings)), ManimEngine)
