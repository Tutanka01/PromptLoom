"""timeline.json: where each scene (and outline section) really sits in the MP4.

The blueprint only carries *planned* durations. The rendered video follows the
voiceover, which is one continuous track muxed at t=0 whose per-scene lengths
are ``audio/en/durations.json`` (the same source captions.py and the visual
review use). The tail padding after the last line belongs to the last scene,
so its end is stretched to the verified duration of the final file.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def build_timeline(
    blueprint: Any,
    durations: dict[str, float],
    video_duration: float | None,
    language: str,
) -> dict[str, Any]:
    scenes: list[dict[str, Any]] = []
    cursor = 0.0
    estimated = False
    for scene in blueprint.scenes:
        seconds = durations.get(scene.key)
        if seconds is None:
            estimated = True
            seconds = float(scene.duration_seconds)
        start = cursor
        cursor += float(seconds)
        scenes.append(
            {
                "scene_key": scene.key,
                "section_id": getattr(scene, "section_id", None),
                "start": round(start, 3),
                "end": round(cursor, 3),
                "title": scene.title,
                "narration": scene.text,
            }
        )
    total = cursor
    if scenes and video_duration and video_duration > 0:
        total = float(video_duration)
        scenes[-1]["end"] = round(max(total, scenes[-1]["start"]), 3)
        for entry in scenes:
            entry["start"] = round(min(entry["start"], total), 3)
            entry["end"] = round(min(entry["end"], total), 3)

    sections: list[dict[str, Any]] = []
    for entry in scenes:
        section_id = entry["section_id"]
        if section_id is None:
            continue
        if sections and sections[-1]["section_id"] == section_id:
            sections[-1]["end"] = entry["end"]
            sections[-1]["scene_keys"].append(entry["scene_key"])
        else:
            sections.append(
                {
                    "section_id": section_id,
                    "start": entry["start"],
                    "end": entry["end"],
                    "scene_keys": [entry["scene_key"]],
                }
            )
    return {
        "version": 1,
        "language": language,
        "duration_seconds": round(total, 3),
        # "voiceover": measured per-scene audio; "planned": at least one scene
        # fell back to its blueprint duration (no durations.json entry).
        "timing_source": "planned" if estimated else "voiceover",
        "scenes": scenes,
        "sections": sections,
    }


def write_timeline(
    workspace: Path,
    video_dir: Path,
    blueprint: Any,
    video_duration: float | None,
    language: str,
) -> str | None:
    """Write ``final/timeline.json`` and return its workspace-relative path
    (served by ``/v1/videos/{id}/artifacts/<path>``). Never raises: a missing
    timeline must not fail a rendered video."""
    try:
        durations_path = video_dir / "audio" / "en" / "durations.json"
        durations: dict[str, float] = {}
        if durations_path.exists():
            raw = json.loads(durations_path.read_text(encoding="utf-8"))
            durations = {str(key): float(value) for key, value in raw.items()}
        timeline = build_timeline(blueprint, durations, video_duration, language)
        path = video_dir / "final" / "timeline.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(timeline, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        logger.info(
            "timeline.done scenes=%d sections=%d duration=%.3f source=%s",
            len(timeline["scenes"]),
            len(timeline["sections"]),
            timeline["duration_seconds"],
            timeline["timing_source"],
        )
        try:
            return str(path.relative_to(workspace))
        except ValueError:
            return str(path)
    except Exception:
        logger.exception("timeline.failed video_dir=%s", video_dir)
        return None
