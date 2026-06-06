from __future__ import annotations

import ast
import json
import logging
import re
import subprocess
from pathlib import Path

from video_api.schemas import CLASS_KEY_RE


logger = logging.getLogger(__name__)


APPROVED_VISUAL_PRIMITIVES = {
    "concept_map",
    "process_flow",
    "layered_system",
    "timeline",
    "equation_transform",
    "graph_plot",
    "comparison_table",
    "cycle_diagram",
    "spatial_model",
    "recap_map",
}


def validate_static_video_source(video_dir: Path) -> None:
    logger.info("validate.start video_dir=%s", video_dir)
    segments_path = video_dir / "segments_en.json"
    beats_path = video_dir / "beats_en.json"
    if not segments_path.exists():
        raise ValueError("segments_en.json missing")
    if not beats_path.exists():
        raise ValueError("beats_en.json missing")

    segments = json.loads(segments_path.read_text(encoding="utf-8"))["segments"]
    beats = json.loads(beats_path.read_text(encoding="utf-8"))
    keys = [segment["key"] for segment in segments]
    logger.info("validate.segments video_dir=%s segments=%d beat_sets=%d", video_dir, len(segments), len(beats))
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate segment keys")
    for segment in segments:
        if segment["key"] != segment["class"]:
            raise ValueError(f"segment key/class mismatch: {segment['key']}")
        if len(str(segment.get("text", "")).split()) < 10:
            raise ValueError(f"segment narration too short: {segment['key']}")
        if not CLASS_KEY_RE.match(segment["key"]):
            raise ValueError(f"invalid segment key: {segment['key']}")
        if segment["key"] not in beats:
            raise ValueError(f"missing beats for {segment['key']}")
        scene_beats = beats[segment["key"]]
        if len(scene_beats) < 3:
            raise ValueError(f"too few beats for {segment['key']}")
        ats = [float(beat["at"]) for beat in scene_beats]
        if ats != sorted(ats):
            raise ValueError(f"beats are not sorted for {segment['key']}")
        if ats[-1] < 0.75:
            raise ValueError(f"last beat too early for {segment['key']}")
        for beat in scene_beats:
            action = str(beat.get("visual_action", "")).strip().lower()
            if action in {"make it nice", "show something", "more explanation", "animate"}:
                raise ValueError(f"vague visual action for {segment['key']}: {action}")

    py_files = list(video_dir.glob("*_en.py")) + list(video_dir.glob("*_style.py")) + [video_dir / "generate_voice_en.py"]
    manim_files = [path for path in video_dir.glob("*_en.py") if path.name != "generate_voice_en.py"]
    for manim_path in manim_files:
        source = manim_path.read_text(encoding="utf-8")
        layouts = re.findall(r'build_layout\("([a-z_]+)"', source)
        unknown = sorted(set(layouts) - APPROVED_VISUAL_PRIMITIVES)
        if unknown:
            raise ValueError(f"generated scenes use unknown visual primitives: {unknown}")
        if len(layouts) >= 4 and len(set(layouts)) < 3:
            raise ValueError("generated scenes use too little visual primitive variety")
        if layouts and layouts.count("process_flow") == len(segments):
            raise ValueError("generated scenes use one generic process flow only")

    for path in py_files:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    subprocess.run(
        ["python3", "-m", "py_compile", *[str(path) for path in py_files]],
        check=True,
        cwd=video_dir,
        capture_output=True,
        text=True,
    )
    logger.info("validate.done video_dir=%s python_files=%d", video_dir, len(py_files))
