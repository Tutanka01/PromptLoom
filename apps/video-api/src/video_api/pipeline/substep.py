"""Sub-step progress reporting for long-running pipeline commands.

`VideoJob.progress` only moves at status transitions (5 → 16 → 40 → 55 → 72 →
92 → 100), so the Studio has no visibility into what's happening between two
transitions. This module bridges that gap: it parses tool output (Remotion
frame counter, OpenAI-compatible TTS segment start, etc.) and writes the
result to the four `substep_*` columns on the video_jobs row so the API can
surface it in `VideoStatusResponse.substep`.

The parsers are pure functions returning a `SubstepUpdate` (or None), so they
are trivially testable. `SubstepReporter` is the runtime glue: rate-limited DB
writes wrapped in a callable suitable as the `on_line` hook of
`CommandRunner.run()`.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from video_api.models import VideoJob


logger = logging.getLogger(__name__)


@dataclass
class SubstepUpdate:
    """Parser output: one unit of measured progress inside a step."""

    current: int
    # None if the tool doesn't announce the total (typical for Manim's
    # per-scene animation stream, where each scene has its own range).
    total: int | None = None
    # Seconds remaining, when the tool provides an ETA (Remotion prints one
    # per frame; Manim does not). Not used to update `current` but stored so
    # the Studio can display "reste Nmin".
    eta_seconds: int | None = None


# ---- Parsers -----------------------------------------------------------------

# Remotion's renderMedia writes one line per frame:
#   "Rendered 3135/4429, time remaining: 3m 38s"
# Sometimes without the ETA when the estimator hasn't warmed up:
#   "Rendered 12/4429"
_REMOTION_FRAME_RE = re.compile(
    r"Rendered\s+(\d+)\s*/\s*(\d+)(?:,\s*time remaining:\s*([\dhms\s]+))?",
    re.IGNORECASE,
)


def parse_remotion_frame(line: str) -> SubstepUpdate | None:
    match = _REMOTION_FRAME_RE.search(line)
    if not match:
        return None
    current = int(match.group(1))
    total = int(match.group(2))
    eta_raw = (match.group(3) or "").strip()
    eta_seconds = _parse_eta_to_seconds(eta_raw) if eta_raw else None
    return SubstepUpdate(current=current, total=total, eta_seconds=eta_seconds)


# generate_voice_en.py prints one "Generating <engine> segment ..." line per
# segment. The engine label varies (Kokoro, Chatterbox, Chatterbox Turbo,
# OpenAI-compatible TTS, MOSS TTS) — match the family so one parser covers
# every voice_engine setting.
_TTS_SEGMENT_RE = re.compile(
    r"Generating (?:Kokoro|Chatterbox(?: Turbo)?|OpenAI-compatible TTS|MOSS TTS) segment",
    re.IGNORECASE,
)


def parse_openai_tts_segment_start(line: str) -> bool:
    """True when the line announces the start of a new TTS segment. Covers
    every generate_voice_en.py engine (openai, kokoro, chatterbox[-turbo], moss);
    the caller holds the running counter — this parser is stateless."""
    return bool(_TTS_SEGMENT_RE.search(line))


# Manim per-scene render marker: `INFO     Rendered Scene1_HookEN` (blueprint
# scene key). Scene keys look like `Scene<N>_<Name><LANG>` where <LANG> is a
# two-letter uppercase code (EN/FR/DE/…) glued to the name — no underscore in
# between. We match that shape so unrelated "Rendered X/Y" lines from Remotion
# (present in mixed logs) don't false-positive here.
_MANIM_SCENE_RENDERED_RE = re.compile(
    r"\bRendered\s+([A-Z][A-Za-z0-9_]*(?:EN|FR|DE|ES|IT|ZH|AR|PT|JA|KO|NL|PL|RU|TR))\b"
)


def parse_manim_scene_done(line: str) -> str | None:
    """Return the scene key when Manim announces a scene finished rendering,
    else None. Same "count against a known total" contract as the TTS parser."""
    match = _MANIM_SCENE_RENDERED_RE.search(line)
    return match.group(1) if match else None


def _parse_eta_to_seconds(value: str) -> int | None:
    """'3m 38s' -> 218 · '45s' -> 45 · '1h 5m' -> 3900. None on parse failure."""
    total = 0
    matched = False
    for number, unit in re.findall(r"(\d+)\s*([hms])", value.lower()):
        matched = True
        n = int(number)
        if unit == "h":
            total += n * 3600
        elif unit == "m":
            total += n * 60
        else:  # 's'
            total += n
    return total if matched else None


# ---- Runtime reporter --------------------------------------------------------


class SubstepReporter:
    """Callable that consumes stdout/stderr lines from `CommandRunner` and
    writes rate-limited sub-step updates to the video_jobs row.

    Instantiate one reporter per long-running command:

        reporter = SubstepReporter(
            session, job,
            unit="frames",
            total=None,               # will be picked up from the first parse
            parse=parse_remotion_frame,
        )
        runner.run(args, cwd=..., log_name="render-final.log", on_line=reporter)
    """

    # 2s is enough to feel live in the Studio (polling is 2.5s anyway) without
    # hammering Postgres — Remotion prints ~1 line per frame at 60 fps, so a
    # 1-minute render is thousands of lines.
    DEFAULT_MIN_INTERVAL_SECONDS = 2.0

    def __init__(
        self,
        session: Session,
        job: VideoJob,
        unit: str,
        parse: Callable[[str], SubstepUpdate | None],
        total: int | None = None,
        min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS,
    ) -> None:
        self._session = session
        self._job = job
        self._unit = unit
        self._parse = parse
        self._initial_total = total
        self._min_interval = min_interval_seconds
        # Start at -inf so the very first parseable line always commits, no
        # matter how small ``time.monotonic()`` happens to be (fresh CI
        # containers can have a monotonic clock a fraction of a second past
        # boot — 0.0 as the sentinel silently swallowed the first tick there).
        self._last_write = float("-inf")
        self._last_current: int | None = None

    def __call__(self, _stream: str, line: str) -> None:
        update = self._parse(line)
        if update is None:
            return
        total = update.total if update.total is not None else self._initial_total
        now = time.monotonic()
        # Always flush the terminal frame (current == total) so the Studio sees
        # 100% right before the status transition. Otherwise batch updates on
        # `min_interval` — Remotion emits ~1 line per frame at 60 fps, so a
        # 1-minute render would otherwise punch thousands of DB writes.
        is_final = total is not None and update.current >= total
        if not is_final and now - self._last_write < self._min_interval:
            return
        self._last_write = now
        self._last_current = update.current
        self._job.substep_unit = self._unit
        self._job.substep_current = int(update.current)
        if total is not None:
            self._job.substep_total = int(total)
        if update.eta_seconds is not None:
            self._job.substep_eta_seconds = int(update.eta_seconds)
        self._session.add(self._job)
        try:
            self._session.commit()
        except Exception:
            # A DB blip must not sink the render. Roll back and keep parsing —
            # the next successful commit will catch us up.
            logger.exception("substep.commit.failed job_id=%s", self._job.id)
            self._session.rollback()


class ManimSceneReporter:
    """Counts Manim's `Rendered SceneName` markers against the known total.
    A scene key seen twice (Manim occasionally re-emits on retry) is only
    counted once."""

    def __init__(
        self,
        session: Session,
        job: VideoJob,
        total_scenes: int,
    ) -> None:
        self._session = session
        self._job = job
        self._total = total_scenes
        self._seen: set[str] = set()

    def __call__(self, _stream: str, line: str) -> None:
        scene_key = parse_manim_scene_done(line)
        if scene_key is None or scene_key in self._seen:
            return
        self._seen.add(scene_key)
        self._job.substep_unit = "scenes"
        self._job.substep_current = len(self._seen)
        self._job.substep_total = self._total
        self._session.add(self._job)
        try:
            self._session.commit()
        except Exception:
            logger.exception("substep.commit.failed job_id=%s", self._job.id)
            self._session.rollback()


class TTSSegmentReporter:
    """Counting reporter for the TTS generate_voice_en.py subprocess. Bumps a
    counter on every "Generating <engine> segment ..." line — covers Kokoro,
    Chatterbox (+ Turbo), OpenAI-compatible TTS and MOSS TTS."""

    def __init__(
        self,
        session: Session,
        job: VideoJob,
        total_segments: int,
        min_interval_seconds: float = 0.0,
    ) -> None:
        self._session = session
        self._job = job
        self._total = total_segments
        self._min_interval = min_interval_seconds
        self._count = 0
        # Same rationale as SubstepReporter: -inf guarantees the very first
        # segment start commits even on a fresh-monotonic-clock CI runner.
        self._last_write = float("-inf")

    def __call__(self, _stream: str, line: str) -> None:
        if not parse_openai_tts_segment_start(line):
            return
        self._count += 1
        now = time.monotonic()
        if now - self._last_write < self._min_interval and self._count < self._total:
            return
        self._last_write = now
        self._job.substep_unit = "segments"
        self._job.substep_current = self._count
        self._job.substep_total = self._total
        self._session.add(self._job)
        try:
            self._session.commit()
        except Exception:
            logger.exception("substep.commit.failed job_id=%s", self._job.id)
            self._session.rollback()


def clear_substep(session: Session, job: VideoJob) -> None:
    """Reset the substep columns; called on status transitions so a stale
    'frames 4429/4429' doesn't linger past the render step."""
    job.substep_unit = None
    job.substep_current = None
    job.substep_total = None
    job.substep_eta_seconds = None
    session.add(job)
    session.commit()


def set_substep(
    session: Session,
    job: VideoJob,
    unit: str,
    current: int,
    total: int,
    eta_seconds: int | None = None,
) -> None:
    """One-shot substep write for steps that already iterate in Python (like
    the per-scene codegen loop). Prefer `SubstepReporter` for subprocess
    output. Commits immediately."""
    job.substep_unit = unit
    job.substep_current = current
    job.substep_total = total
    job.substep_eta_seconds = eta_seconds
    session.add(job)
    session.commit()
