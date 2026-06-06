from __future__ import annotations

import ast
import json
import logging
import subprocess
from pathlib import Path

from video_api.schemas import CLASS_KEY_RE


logger = logging.getLogger(__name__)


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
        if not CLASS_KEY_RE.match(segment["key"]):
            raise ValueError(f"invalid segment key: {segment['key']}")
        if segment["key"] not in beats:
            raise ValueError(f"missing beats for {segment['key']}")

    py_files = list(video_dir.glob("*_en.py")) + list(video_dir.glob("*_style.py")) + [video_dir / "generate_voice_en.py"]
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
