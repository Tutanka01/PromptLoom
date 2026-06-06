from __future__ import annotations

from video_api.pipeline.llm import _extract_json_object, _strip_reasoning
from video_api.schemas import BeatSpec, _short_label


def test_strip_reasoning_removes_think_block() -> None:
    raw = '<think>The user wants JSON. Let me plan...</think>\n{"ok": true}'
    assert _strip_reasoning(raw) == '{"ok": true}'


def test_extract_json_object_ignores_inline_reasoning() -> None:
    raw = "<think>reasoning here</think> some prose {\"a\": 1, \"b\": [2, 3]} trailing"
    assert _extract_json_object(raw) == {"a": 1, "b": [2, 3]}


def test_beat_label_derived_from_text_hint_when_missing() -> None:
    beat = BeatSpec(key="k1", at=0.1, text_hint="how fast is something changing", visual_action="Reveal the card.")
    assert beat.label == "how fast is something changing"


def test_beat_label_never_keeps_instruction_when_explicit() -> None:
    beat = BeatSpec(
        key="k2",
        at=0.2,
        text_hint="slope of a secant line",
        visual_action="Create the secant line through both points.",
        label="secant slope",
    )
    assert beat.label == "secant slope"


def test_short_label_clips_at_word_boundary_without_mid_word_cut() -> None:
    label = _short_label("models are built from changing quantities everywhere")
    assert len(label) <= 41  # 40 + ellipsis
    assert label.endswith("…")
    assert not label[:-1].endswith(" ")
