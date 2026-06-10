"""Resolve Remotion blueprint beat anchors into per-scene visual cue ratios.

A blueprint scene may declare ``beats``: short phrases copied from its own
narration, one per visual item in display order. After TTS + forced alignment
(pipeline/align.py), this module locates each anchor in the aligned words and
converts its start time into a ratio of the scene's *padded* duration — the
same durations.json number that build_video_json.py turns into
durationInFrames, so a cue ratio maps exactly onto the React progress p.

The resolved ``cues`` array (number | null per beat) is injected into the
scene's props in scenes_map.json. ``null`` means "anchor not matched
confidently": the React component falls back to its default timing for that
index only. Cues are forced ascending so items never reveal out of order.
"""
from __future__ import annotations

import difflib
import json
import logging
from pathlib import Path
from typing import Any

from video_api.pipeline.align import normalize_words

logger = logging.getLogger(__name__)

# Keep cues inside the scene body: never before the settle-in, never inside the
# tail fade (scenes dissolve out over the last ~7% of their duration).
CUE_MIN = 0.05
CUE_MAX = 0.88
MATCH_THRESHOLD = 0.8


def find_anchor(words: list[dict[str, Any]], anchor: str) -> float | None:
    """Best fuzzy match of *anchor* in the aligned words; returns start seconds.

    Sliding window of the anchor's length over the word sequence, scored with
    SequenceMatcher on the normalized joined text (tolerates small TTS/LLM
    drift: a paraphrased word, a dropped article). Below MATCH_THRESHOLD the
    anchor is considered absent.
    """
    target_words = normalize_words(anchor)
    if not target_words or not words:
        return None
    target = " ".join(target_words)
    best_score = 0.0
    best_start: float | None = None
    # Window sizes n-1..n+1: tolerate one word inserted or dropped between the
    # anchor and what the TTS actually spoke (a stray article, a contraction).
    base = min(len(target_words), len(words))
    for n in {max(1, base - 1), base, min(len(words), base + 1)}:
        for i in range(len(words) - n + 1):
            window = words[i : i + n]
            candidate = " ".join(str(w["w"]) for w in window)
            score = difflib.SequenceMatcher(None, candidate, target).ratio()
            if score > best_score:
                best_score = score
                best_start = float(window[0]["start"])
    return best_start if best_score >= MATCH_THRESHOLD else None


def anchor_in_text(text: str, anchor: str) -> bool:
    """True if *anchor* fuzzy-matches somewhere in *text* (pre-TTS validation).

    Reuses the exact matcher used against the aligned audio, with word indices
    standing in for timestamps — so "will this anchor resolve to a cue later?"
    is answered by the same logic that will resolve it.
    """
    words = [{"w": w, "start": float(i)} for i, w in enumerate(normalize_words(text))]
    return find_anchor(words, anchor) is not None


def _scene_cues(
    beats: list[Any],
    words: list[dict[str, Any]],
    duration: float,
) -> list[float | None]:
    cues: list[float | None] = []
    floor = CUE_MIN
    for beat in beats:
        anchor = getattr(beat, "anchor", None) or (beat.get("anchor") if isinstance(beat, dict) else "")
        start = find_anchor(words, str(anchor or ""))
        if start is None:
            cues.append(None)
            continue
        ratio = min(CUE_MAX, max(CUE_MIN, start / duration))
        # Ascending order: a cue that would jump backwards (likely a repeated
        # phrase matched too early) is pinned just after the previous one.
        if ratio < floor:
            ratio = min(CUE_MAX, floor)
        cues.append(round(ratio, 4))
        floor = ratio + 0.02
    return cues


def resolve_cues(video_dir: Path, blueprint: Any) -> dict[str, list[float | None]]:
    """Compute cues for every scene with beats and inject them into scenes_map.json.

    Returns {scene_key: cues} for the scenes that got at least one resolved cue.
    Missing alignment/durations files mean "nothing to do" (default timings).
    """
    audio_dir = video_dir / "audio" / "en"
    alignment_path = audio_dir / "alignment.json"
    durations_path = audio_dir / "durations.json"
    if not alignment_path.exists() or not durations_path.exists():
        logger.warning(
            "beats.skip alignment=%s durations=%s",
            alignment_path.exists(),
            durations_path.exists(),
        )
        return {}
    alignment = json.loads(alignment_path.read_text(encoding="utf-8"))
    durations = json.loads(durations_path.read_text(encoding="utf-8"))

    cues_by_key: dict[str, list[float | None]] = {}
    for scene in blueprint.scenes:
        beats = getattr(scene, "beats", None) or []
        if not beats:
            continue
        words = (alignment.get(scene.key) or {}).get("words") or []
        duration = float(durations.get(scene.key) or 0.0)
        if not words or duration <= 0:
            continue
        cues = _scene_cues(beats, words, duration)
        if any(cue is not None for cue in cues):
            cues_by_key[scene.key] = cues

    if cues_by_key:
        _inject_cues(video_dir / "scenes_map.json", cues_by_key)
    logger.info(
        "beats.resolved scenes_with_beats=%d scenes_with_cues=%d",
        sum(1 for s in blueprint.scenes if getattr(s, "beats", None)),
        len(cues_by_key),
    )
    return cues_by_key


def _inject_cues(scenes_map_path: Path, cues_by_key: dict[str, list[float | None]]) -> None:
    scene_map = json.loads(scenes_map_path.read_text(encoding="utf-8"))
    for entry in scene_map["scenes"]:
        cues = cues_by_key.get(entry["key"])
        if cues is not None:
            entry.setdefault("props", {})["cues"] = cues
    scenes_map_path.write_text(json.dumps(scene_map, indent=2) + "\n", encoding="utf-8")
