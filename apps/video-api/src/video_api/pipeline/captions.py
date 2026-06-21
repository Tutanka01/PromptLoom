"""Subtitle authoring: turn aligned surface words into broadcast-quality cues.

This is the single source of truth for *what the subtitles say and when*. The
forced aligner (pipeline/align.py) projects timings onto the real surface words
(``alignment.json`` -> per-scene ``captions``: {"text","start","end"} with
correct case, punctuation and accents). This module groups those words into
**cues** — 1-2 short lines broken on sense boundaries, with a bounded on-screen
duration — and emits them two ways from the same grouping so they can never drift:

- ``captionCues`` injected into ``scenes_map.json`` props (scene-relative) and
  rendered, word-synced, by Remotion's ``NarrationCaptions``;
- a global ``final/<slug>-<lang>.srt`` + ``.vtt`` sidecar, offsetting each scene
  by the cumulative voiceover duration (the voiceover is one continuous track
  muxed at t=0, so the spoken timeline is the sum of ``durations.json``).

``build_cues`` is a pure function (no I/O) so the segmentation rules stay testable
in isolation.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Sentence/clause closers we prefer to break a cue on. Trailing quotes/brackets
# after the mark (e.g. `."`, `?)`) still count as a sentence end.
_SENTENCE_END = ".!?:;…"
_TRAILING = "\"')]»”’"


def _ends_sentence(text: str) -> bool:
    stripped = text.rstrip(_TRAILING)
    return bool(stripped) and stripped[-1] in _SENTENCE_END


def _pack_lines(tokens: list[dict], max_line: int) -> list[list[dict]]:
    """Greedy word wrap into lines of at most ``max_line`` characters.

    A single word longer than ``max_line`` gets its own (over-long) line rather
    than being split mid-word.
    """
    lines: list[list[dict]] = []
    current: list[dict] = []
    length = 0
    for tok in tokens:
        width = len(tok["text"])
        added = width + (1 if current else 0)
        if current and length + added > max_line:
            lines.append(current)
            current = [tok]
            length = width
        else:
            current.append(tok)
            length += added
    if current:
        lines.append(current)
    return lines


def _wrap_balanced(tokens: list[dict], max_line: int) -> list[list[dict]]:
    """Wrap into display lines, balancing the two-line case.

    Greedy packing decides how many lines are needed; when that is exactly two,
    re-pick the break point to minimise the length gap between the lines (both
    still within ``max_line``), so we never leave a lone orphan word on line two.
    Other cases (one line, or the rare >2) keep the greedy packing.
    """
    greedy = _pack_lines(tokens, max_line)
    if len(greedy) != 2:
        return greedy
    texts = [t["text"] for t in tokens]
    best_k: int | None = None
    best_gap = None
    for k in range(1, len(tokens)):
        first = " ".join(texts[:k])
        second = " ".join(texts[k:])
        if len(first) > max_line or len(second) > max_line:
            continue
        gap = abs(len(first) - len(second))
        if best_gap is None or gap < best_gap:
            best_gap, best_k = gap, k
    if best_k is None:
        return greedy
    return [tokens[:best_k], tokens[best_k:]]


def _make_cue(tokens: list[dict], max_line: int) -> dict:
    lines = _wrap_balanced(tokens, max_line)
    return {
        "start": float(tokens[0]["start"]),
        "end": float(tokens[-1]["end"]),
        "lines": [
            [{"text": t["text"], "start": float(t["start"]), "end": float(t["end"])} for t in line]
            for line in lines
        ],
    }


def build_cues(
    tokens: list[dict],
    *,
    max_line: int = 42,
    max_lines: int = 2,
    min_dur: float = 0.8,
    max_dur: float = 6.0,
    min_cue_chars: int = 16,
) -> list[dict]:
    """Group surface caption tokens into readable cues.

    Rules (in priority order):
      * never exceed ``max_lines`` lines of ``max_line`` chars (close the cue
        before a token that would overflow the wrap);
      * never let a cue span more than ``max_dur`` seconds;
      * prefer to close on sentence/clause punctuation, but only once the cue
        holds at least ``min_cue_chars`` so tiny fragments don't flash alone;
      * extend a too-short cue toward ``min_dur`` without overlapping the next.

    Returns JSON-ready cue dicts: {"start","end","lines":[[{"text","start","end"}]]}.
    """
    cues: list[dict] = []
    current: list[dict] = []

    def flush() -> None:
        if current:
            cues.append(_make_cue(current, max_line))
            current.clear()

    for tok in tokens:
        trial = current + [tok]
        overflow_lines = len(_pack_lines(trial, max_line)) > max_lines
        overflow_dur = bool(current) and (tok["end"] - current[0]["start"]) > max_dur
        if current and (overflow_lines or overflow_dur):
            flush()
        current.append(tok)
        chars = sum(len(t["text"]) for t in current) + (len(current) - 1)
        if _ends_sentence(tok["text"]) and chars >= min_cue_chars:
            flush()
    flush()

    # Extend short cues toward a comfortable minimum display time, but never
    # past the next cue's start (keeps the burned-in track and SRT non-overlapping).
    for i, cue in enumerate(cues):
        next_start = cues[i + 1]["start"] if i + 1 < len(cues) else None
        target = cue["start"] + min_dur
        if next_start is not None:
            target = min(target, next_start)
        cue["end"] = round(max(cue["end"], target), 3)
    return cues


def _fmt_ts(seconds: float, sep: str) -> str:
    ms = max(0, round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _cue_text(cue: dict) -> str:
    return "\n".join(" ".join(w["text"] for w in line) for line in cue["lines"])


def _render_srt(cues: list[dict]) -> str:
    blocks = []
    for index, cue in enumerate(cues, start=1):
        start = _fmt_ts(cue["start"], ",")
        end = _fmt_ts(cue["end"], ",")
        blocks.append(f"{index}\n{start} --> {end}\n{_cue_text(cue)}\n")
    return "\n".join(blocks)


def _render_vtt(cues: list[dict]) -> str:
    blocks = ["WEBVTT\n"]
    for cue in cues:
        start = _fmt_ts(cue["start"], ".")
        end = _fmt_ts(cue["end"], ".")
        blocks.append(f"{start} --> {end}\n{_cue_text(cue)}\n")
    return "\n".join(blocks)


def _offset_cue(cue: dict, offset: float, hard_end: float | None) -> dict:
    """Shift a scene-relative cue onto the global (whole-video) timeline.

    Word timings are offset too, not just the cue window, so the burned-in
    karaoke highlight and the .srt stay in sync on the global timeline.
    """
    end = cue["end"] + offset
    if hard_end is not None:
        end = min(end, hard_end)
    return {
        "start": round(cue["start"] + offset, 3),
        "end": round(max(cue["start"] + offset, end), 3),
        "lines": [
            [
                {
                    "text": w["text"],
                    "start": round(w["start"] + offset, 3),
                    "end": round(w["end"] + offset, 3),
                }
                for w in line
            ]
            for line in cue["lines"]
        ],
    }


def write_subtitles(video_dir: Path, *, slug: str, language: str) -> int:
    """Build one global cue list for the whole video; write it + the SRT/VTT.

    Reads ``scenes_map.json`` (scene order), ``alignment.json`` (surface captions)
    and ``durations.json`` (per-scene voiceover seconds). Each scene's cues are
    shifted onto the global timeline by the cumulative voiceover duration (the
    voiceover is one continuous track muxed at t=0). The result is written to
    ``subtitles.json`` — consumed by Remotion as a single continuous, top-level
    subtitle track (NOT gated per scene/beat) — and to ``final/<slug>-<language>``
    ``.srt`` / ``.vtt``. Returns the number of cues. Missing alignment/durations
    is a no-op (returns 0): captions are best-effort.
    """
    audio_dir = video_dir / "audio" / "en"
    alignment_path = audio_dir / "alignment.json"
    durations_path = audio_dir / "durations.json"
    scenes_map_path = video_dir / "scenes_map.json"
    if not (alignment_path.exists() and durations_path.exists() and scenes_map_path.exists()):
        logger.warning(
            "captions.skip alignment=%s durations=%s scenes_map=%s",
            alignment_path.exists(),
            durations_path.exists(),
            scenes_map_path.exists(),
        )
        return 0

    alignment = json.loads(alignment_path.read_text(encoding="utf-8"))
    durations = json.loads(durations_path.read_text(encoding="utf-8"))
    scene_map = json.loads(scenes_map_path.read_text(encoding="utf-8"))

    global_cues: list[dict] = []
    offset = 0.0
    for entry in scene_map["scenes"]:
        key = entry["key"]
        duration = float(durations.get(key, 0.0))
        captions = (alignment.get(key) or {}).get("captions") or []
        cues = build_cues(captions) if captions else []
        if cues:
            hard_end = offset + duration if duration > 0 else None
            global_cues.extend(_offset_cue(cue, offset, hard_end) for cue in cues)
        offset += duration

    # The continuous track always reads subtitles.json; write it even when empty
    # so build_video_json has a stable contract.
    (video_dir / "subtitles.json").write_text(
        json.dumps({"cues": global_cues}, indent=2) + "\n", encoding="utf-8"
    )

    if not global_cues:
        logger.warning("captions.empty slug=%s lang=%s", slug, language)
        return 0

    final_dir = video_dir / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    (final_dir / f"{slug}-{language}.srt").write_text(_render_srt(global_cues), encoding="utf-8")
    (final_dir / f"{slug}-{language}.vtt").write_text(_render_vtt(global_cues), encoding="utf-8")
    logger.info(
        "captions.done scenes=%d cues=%d slug=%s lang=%s",
        len(scene_map["scenes"]),
        len(global_cues),
        slug,
        language,
    )
    return len(global_cues)
