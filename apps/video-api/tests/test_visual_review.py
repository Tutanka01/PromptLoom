from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any
from unittest.mock import MagicMock

import pytest

from video_api.pipeline.visual_review import (
    VisualReviewer,
    _compute_score,
    _parse_review_response,
    _scene_midpoints,
)
from video_api.schemas import (
    VisualReviewResult,
    _DIMENSION_WEIGHTS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_blueprint(scene_keys: list[str], duration_per_scene: int = 30):
    """Build a minimal VideoBlueprint-like namespace for testing."""
    scenes = []
    for i, key in enumerate(scene_keys, start=1):
        scene = MagicMock()
        scene.key = key
        scene.text = f"Narration for {key}."
        scene.visual_intent = f"Show concept for {key}."
        scene.duration_seconds = duration_per_scene
        beat = MagicMock()
        beat.key = "main"
        beat.at = 0.5
        beat.text_hint = "Core idea"
        beat.visual_action = "Reveal diagram"
        scene.beats = [beat]
        scenes.append(scene)
    bp = MagicMock()
    bp.scenes = scenes
    return bp


class FakeRunner:
    def run(self, args: list[str], cwd: Path, log_name: str, env: Any = None) -> CompletedProcess:
        # Simulate ffmpeg frame extraction: write a tiny PNG stub
        if args[0] == "ffmpeg" and "-frames:v" in args:
            Path(args[-1]).write_bytes(b"\x89PNG\r\n\x1a\n")
        return CompletedProcess(args, 0, stdout="", stderr="")


# ---------------------------------------------------------------------------
# Test 1: weighted scoring is deterministic
# ---------------------------------------------------------------------------

def test_compute_score_all_tens():
    dims = {dim: 10.0 for dim in _DIMENSION_WEIGHTS}
    score = _compute_score(dims)
    assert score == 100.0


def test_compute_score_all_zeros():
    dims = {dim: 0.0 for dim in _DIMENSION_WEIGHTS}
    score = _compute_score(dims)
    assert score == 0.0


def test_compute_score_weights_sum_to_one():
    total_weight = sum(_DIMENSION_WEIGHTS.values())
    assert abs(total_weight - 1.0) < 1e-9


def test_compute_score_partial():
    # Only narration_match = 10 (weight 0.35), all others 0 → 10 * 0.35 * 10 = 35
    dims = {dim: 0.0 for dim in _DIMENSION_WEIGHTS}
    dims["narration_match"] = 10.0
    score = _compute_score(dims)
    assert abs(score - 35.0) < 0.01


# ---------------------------------------------------------------------------
# Test 2: blocker rule — a blocker forces passed=False even above threshold
# ---------------------------------------------------------------------------

def test_blocker_forces_failure():
    bp = _make_blueprint(["Scene1_HookEN"])
    raw = {
        "scene_scores": [
            {"scene_key": "Scene1_HookEN", "dimensions": {d: 10.0 for d in _DIMENSION_WEIGHTS}},
        ],
        "issues": [
            {
                "scene_key": "Scene1_HookEN",
                "dimension": "readability",
                "severity": "blocker",
                "message": "Text clipped at right edge",
                "suggestion": "Shorten label",
            }
        ],
        "summary": "Good video but one blocker.",
    }
    midpoints = [(bp.scenes[0], 15.0)]
    result = _parse_review_response(raw, midpoints, min_score=75.0)
    assert result.score == 100.0
    assert result.passed is False
    assert any(i.severity == "blocker" for i in result.issues)


def test_no_blocker_above_threshold_passes():
    bp = _make_blueprint(["Scene1_HookEN"])
    raw = {
        "scene_scores": [
            {"scene_key": "Scene1_HookEN", "dimensions": {d: 9.0 for d in _DIMENSION_WEIGHTS}},
        ],
        "issues": [
            {
                "scene_key": "Scene1_HookEN",
                "dimension": "density",
                "severity": "minor",
                "message": "Slightly busy",
                "suggestion": "Remove one element",
            }
        ],
        "summary": "Great video.",
    }
    midpoints = [(bp.scenes[0], 15.0)]
    result = _parse_review_response(raw, midpoints, min_score=75.0)
    assert result.passed is True


def test_unknown_severity_is_normalized_not_dropped():
    # A vision model returning a non-standard severity must not lose the issue.
    bp = _make_blueprint(["Scene1_HookEN"])
    raw = {
        "scene_scores": [
            {"scene_key": "Scene1_HookEN", "dimensions": {d: 9.0 for d in _DIMENSION_WEIGHTS}},
        ],
        "issues": [
            {"scene_key": "Scene1_HookEN", "dimension": "framing", "severity": "critical",
             "message": "Element off-screen", "suggestion": "Move it inward"},
        ],
        "summary": "One non-standard severity.",
    }
    midpoints = [(bp.scenes[0], 15.0)]
    result = _parse_review_response(raw, midpoints, min_score=75.0)
    assert len(result.issues) == 1
    assert result.issues[0].severity == "major"  # "critical" coerced to major, not dropped


def test_low_score_below_threshold_fails():
    bp = _make_blueprint(["Scene1_HookEN"])
    raw = {
        "scene_scores": [
            {"scene_key": "Scene1_HookEN", "dimensions": {d: 5.0 for d in _DIMENSION_WEIGHTS}},
        ],
        "issues": [],
        "summary": "Mediocre.",
    }
    midpoints = [(bp.scenes[0], 15.0)]
    result = _parse_review_response(raw, midpoints, min_score=75.0)
    assert result.passed is False
    assert result.score == 50.0


# ---------------------------------------------------------------------------
# Test 3: scene midpoint mapping uses durations.json and falls back correctly
# ---------------------------------------------------------------------------

def test_scene_midpoints_from_durations_json(tmp_path: Path):
    bp = _make_blueprint(["Scene1_HookEN", "Scene2_CoreEN"], duration_per_scene=30)
    durations_path = tmp_path / "durations.json"
    durations_path.write_text(json.dumps({"Scene1_HookEN": 20.0, "Scene2_CoreEN": 40.0}))

    midpoints, total = _scene_midpoints(bp, durations_path)
    assert len(midpoints) == 2
    assert abs(total - 60.0) < 0.01  # 20 + 40
    scene0, ts0 = midpoints[0]
    scene1, ts1 = midpoints[1]
    assert scene0.key == "Scene1_HookEN"
    assert abs(ts0 - 10.0) < 0.01  # 0 + 20/2
    assert scene1.key == "Scene2_CoreEN"
    assert abs(ts1 - 40.0) < 0.01  # 20 + 40/2


def test_scene_midpoints_fallback_when_no_durations_json(tmp_path: Path):
    bp = _make_blueprint(["Scene1_HookEN", "Scene2_CoreEN"], duration_per_scene=25)
    missing = tmp_path / "nope.json"

    midpoints, total = _scene_midpoints(bp, missing)
    assert len(midpoints) == 2
    assert abs(total - 50.0) < 0.01  # 25 + 25 (fallback to planned durations)
    _, ts0 = midpoints[0]
    _, ts1 = midpoints[1]
    assert abs(ts0 - 12.5) < 0.01   # 0 + 25/2
    assert abs(ts1 - 37.5) < 0.01   # 25 + 25/2


# ---------------------------------------------------------------------------
# Test 4: review with mocked vision client
# ---------------------------------------------------------------------------

def _make_settings(tmp_path: Path, enabled: bool = True):
    s = MagicMock()
    s.visual_review_enabled = enabled
    s.visual_review_model = "vision-test-model"
    s.visual_review_min_score = 75.0
    s.visual_review_max_tokens = 500
    s.openai_api_key = "fake-key"
    s.openai_base_url = None
    s.openai_model = "fallback-model"
    s.llm_timeout_seconds = 30
    return s


def _fake_vision_response(raw: dict) -> MagicMock:
    """Build a mock OpenAI chat completion response."""
    choice = MagicMock()
    choice.message.content = json.dumps(raw)
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def test_review_builds_multimodal_message_and_parses_result(tmp_path: Path):
    bp = _make_blueprint(["Scene1_HookEN", "Scene2_CoreEN"], duration_per_scene=30)
    settings = _make_settings(tmp_path)
    runner = FakeRunner()

    # Prepare a fake video file and durations.json
    video_dir = tmp_path / "final"
    video_dir.mkdir()
    video_path = video_dir / "test-en-final.mp4"
    video_path.write_bytes(b"mp4")
    audio_dir = tmp_path / "audio" / "en"
    audio_dir.mkdir(parents=True)
    (audio_dir / "durations.json").write_text(
        json.dumps({"Scene1_HookEN": 30.0, "Scene2_CoreEN": 30.0})
    )

    lm_response = {
        "scene_scores": [
            {"scene_key": "Scene1_HookEN", "dimensions": {d: 8.0 for d in _DIMENSION_WEIGHTS}},
            {"scene_key": "Scene2_CoreEN", "dimensions": {d: 9.0 for d in _DIMENSION_WEIGHTS}},
        ],
        "issues": [],
        "summary": "Solid video.",
    }

    reviewer = VisualReviewer(settings)
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_vision_response(lm_response)
    reviewer._client = fake_client

    result = reviewer.review(bp, video_path, runner, tmp_path / "reports")

    assert isinstance(result, VisualReviewResult)
    assert len(result.scene_scores) == 2
    assert result.score > 0
    assert result.passed is True

    # Verify the multimodal message was constructed with text + image blocks
    call_kwargs = fake_client.chat.completions.create.call_args
    messages = call_kwargs[1]["messages"] if call_kwargs[1] else call_kwargs[0][0]
    # Find the user message content
    user_msg = next(m for m in messages if m["role"] == "user")
    content = user_msg["content"]
    assert any(block.get("type") == "image_url" for block in content), "Expected image_url blocks in message"
    assert any(block.get("type") == "text" for block in content), "Expected text blocks in message"


# ---------------------------------------------------------------------------
# Test 5: repair_hint groups issues by scene
# ---------------------------------------------------------------------------

def test_repair_hint_format():
    result = VisualReviewResult(
        score=45.0,
        passed=False,
        scene_scores=[],
        issues=[
            {"scene_key": "Scene1_HookEN", "dimension": "narration_match", "severity": "blocker",
             "message": "Image shows kernel internals but narration talks about syscalls",
             "suggestion": "Change visual_intent to syscall flow diagram"},
            {"scene_key": "Scene2_CoreEN", "dimension": "readability", "severity": "major",
             "message": "Label truncated", "suggestion": "Shorten label"},
        ],
        summary="Two scenes need fixing.",
    )
    hint = result.repair_hint()
    assert "45.0/100" in hint
    assert "Scene1_HookEN" in hint
    assert "BLOCKER" in hint
    assert "syscall" in hint


def test_repair_hint_no_critical_issues():
    result = VisualReviewResult(
        score=70.0,
        passed=False,
        scene_scores=[],
        issues=[
            {"scene_key": "Scene1_HookEN", "dimension": "density", "severity": "minor",
             "message": "Slightly busy", "suggestion": ""},
        ],
        summary="Minor issues.",
    )
    hint = result.repair_hint()
    assert "70.0/100" in hint
    assert "no major issues" in hint
