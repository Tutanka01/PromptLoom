"""Unit tests for the sub-step progress helpers (parsers + reporters)."""
from __future__ import annotations

import time
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from video_api.pipeline import substep


# ---- Parsers -----------------------------------------------------------------


def test_parse_remotion_frame_with_eta() -> None:
    result = substep.parse_remotion_frame("Rendered 3135/4429, time remaining: 3m 38s")
    assert result is not None
    assert result.current == 3135
    assert result.total == 4429
    assert result.eta_seconds == 3 * 60 + 38


def test_parse_remotion_frame_without_eta() -> None:
    # The estimator prints "Rendered X/Y" without ETA before it warms up.
    result = substep.parse_remotion_frame("Rendered 12/4429")
    assert result is not None
    assert (result.current, result.total, result.eta_seconds) == (12, 4429, None)


def test_parse_remotion_frame_returns_none_on_noise() -> None:
    assert substep.parse_remotion_frame("Compiling bundle...") is None
    assert substep.parse_remotion_frame("") is None


def test_parse_openai_tts_segment_start() -> None:
    assert substep.parse_openai_tts_segment_start(
        "Generating OpenAI-compatible TTS segment Scene1_HookEN with model qwen-clone"
    )
    assert not substep.parse_openai_tts_segment_start("ffmpeg version 7.1.5-0+deb13u1")


def test_eta_parser_handles_hours_minutes_seconds() -> None:
    assert substep._parse_eta_to_seconds("45s") == 45
    assert substep._parse_eta_to_seconds("3m 38s") == 3 * 60 + 38
    assert substep._parse_eta_to_seconds("1h 5m") == 3600 + 5 * 60
    assert substep._parse_eta_to_seconds("garbage") is None


# ---- Reporters ---------------------------------------------------------------


@dataclass
class _FakeJob:
    id: str = "test-job"
    substep_unit: str | None = None
    substep_current: int | None = None
    substep_total: int | None = None
    substep_eta_seconds: int | None = None


def _fake_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = MagicMock()
    session.rollback = MagicMock()
    return session


def test_substep_reporter_updates_after_first_line() -> None:
    job = _FakeJob()
    session = _fake_session()
    reporter = substep.SubstepReporter(
        session, job, unit="frames", parse=substep.parse_remotion_frame
    )
    reporter("stdout", "Rendered 100/4429, time remaining: 4m 0s")
    assert job.substep_unit == "frames"
    assert job.substep_current == 100
    assert job.substep_total == 4429
    assert job.substep_eta_seconds == 240
    assert session.commit.call_count == 1


def test_substep_reporter_rate_limits_within_interval() -> None:
    job = _FakeJob()
    session = _fake_session()
    reporter = substep.SubstepReporter(
        session, job, unit="frames", parse=substep.parse_remotion_frame,
        min_interval_seconds=10.0,
    )
    reporter("stdout", "Rendered 100/4429")
    reporter("stdout", "Rendered 101/4429")
    reporter("stdout", "Rendered 102/4429")
    # Only the first line should have triggered a commit.
    assert session.commit.call_count == 1
    assert job.substep_current == 100


def test_substep_reporter_always_flushes_final_frame() -> None:
    """Even inside the rate-limit window, the last-frame line must commit so
    the Studio doesn't stall at 99% before the status transition."""
    job = _FakeJob()
    session = _fake_session()
    reporter = substep.SubstepReporter(
        session, job, unit="frames", parse=substep.parse_remotion_frame,
        min_interval_seconds=60.0,
    )
    reporter("stdout", "Rendered 4428/4429")
    assert session.commit.call_count == 1
    reporter("stdout", "Rendered 4429/4429")
    # Final frame flushed despite the 60s rate-limit.
    assert session.commit.call_count == 2
    assert job.substep_current == 4429


def test_substep_reporter_ignores_unparseable_noise() -> None:
    job = _FakeJob()
    session = _fake_session()
    reporter = substep.SubstepReporter(
        session, job, unit="frames", parse=substep.parse_remotion_frame
    )
    reporter("stdout", "Compiling bundle...")
    reporter("stdout", "webpack compiled successfully")
    assert session.commit.call_count == 0
    assert job.substep_current is None


def test_substep_reporter_survives_db_failure() -> None:
    job = _FakeJob()
    session = _fake_session()
    session.commit.side_effect = RuntimeError("connection lost")
    reporter = substep.SubstepReporter(
        session, job, unit="frames", parse=substep.parse_remotion_frame
    )
    # Should not raise; the render must keep going.
    reporter("stdout", "Rendered 500/4429, time remaining: 3m")
    session.rollback.assert_called_once()


def test_tts_segment_reporter_counts_per_line() -> None:
    job = _FakeJob()
    session = _fake_session()
    reporter = substep.TTSSegmentReporter(session, job, total_segments=3)
    reporter("stdout", "Generating OpenAI-compatible TTS segment Scene1_HookEN with model qwen-clone")
    reporter("stdout", "Generating OpenAI-compatible TTS segment Scene2_CoreIdeaEN with model qwen-clone")
    reporter("stdout", "ffmpeg version 7.1.5-0+deb13u1")  # not counted
    reporter("stdout", "Generating OpenAI-compatible TTS segment Scene3_RecapEN with model qwen-clone")
    assert job.substep_unit == "segments"
    assert job.substep_current == 3
    assert job.substep_total == 3


def test_clear_substep_resets_all_four_columns() -> None:
    job = _FakeJob(substep_unit="frames", substep_current=100, substep_total=200, substep_eta_seconds=60)
    session = _fake_session()
    substep.clear_substep(session, job)
    assert job.substep_unit is None
    assert job.substep_current is None
    assert job.substep_total is None
    assert job.substep_eta_seconds is None
    session.commit.assert_called_once()
