from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Single source of truth for duration / narration accounting.
#
# Three layers must agree on "how long will this video be":
#   1. schemas.VideoBlueprint  -> pre-flight check on the LLM blueprint (cheap)
#   2. pipeline.verify.verify_mp4 -> final gate on the rendered MP4 (expensive)
#   3. pipeline.llm prompt      -> guidance handed to the model
#
# Keeping the formulas here guarantees the invariant:
#   a blueprint that PASSES validation will produce a video that CLEARS the gate.
# Previously the pre-flight check (0.55 x target, 155 wpm) was looser than the
# final gate (0.75 x target), so blueprints validated, rendered short, then got
# rejected after the costly TTS + Manim render.
# ---------------------------------------------------------------------------

DEFAULT_TARGET_DURATION_SECONDS = 240
DEFAULT_MIN_DURATION_SECONDS = 180

# Words per minute used to translate a narration script into an estimated spoken
# duration. The local TTS (Chatterbox non-turbo) speaks deliberately slowly, so a
# slightly high WPM makes this estimate a CONSERVATIVE LOWER BOUND on the real
# audio length: if the estimate clears the gate, the rendered audio will too.
ESTIMATION_WPM = 160

_WORD_RE = re.compile(r"\b[\w'-]+\b")


def word_count(text: str) -> int:
    return len(_WORD_RE.findall(text))


def estimated_spoken_seconds(text: str) -> int:
    """Conservative estimate of how long `text` takes to narrate."""
    return max(1, round(word_count(text) / ESTIMATION_WPM * 60))


def words_for_seconds(seconds: float) -> int:
    """Inverse of `estimated_spoken_seconds`: words needed to fill `seconds`."""
    return max(1, round(seconds * ESTIMATION_WPM / 60))


def minimum_final_duration(
    target_duration_seconds: int,
    default_min_duration_seconds: int = DEFAULT_MIN_DURATION_SECONDS,
) -> int:
    """Lower bound (seconds) the rendered video must clear in `verify_mp4`."""
    if 180 <= target_duration_seconds <= 300:
        return max(default_min_duration_seconds, int(target_duration_seconds * 0.75))
    return max(45, int(target_duration_seconds * 0.75))


def required_narration_seconds(
    target_duration_seconds: int,
    default_min_duration_seconds: int = DEFAULT_MIN_DURATION_SECONDS,
) -> int:
    """Estimated narration a blueprint must contain so the rendered video clears
    the final gate.

    Equal to the gate itself: the conservative WPM, plus the extra wall-clock
    time added by inter-scene holds and fade-outs, provide the safety margin.
    """
    return minimum_final_duration(target_duration_seconds, default_min_duration_seconds)


def required_total_words(
    target_duration_seconds: int,
    default_min_duration_seconds: int = DEFAULT_MIN_DURATION_SECONDS,
) -> int:
    """Total narration words a blueprint must contain across all scenes."""
    return words_for_seconds(
        required_narration_seconds(target_duration_seconds, default_min_duration_seconds)
    )
