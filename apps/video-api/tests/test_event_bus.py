"""Unit tests for the SSE event-bus glue.

The Redis client is exercised end-to-end in the docker integration test suite;
here we only cover the pure serialisation + channel-naming logic and the
graceful-degradation guarantees (missing repair/substep columns must not
crash ``snapshot_of``).
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from video_api import event_bus


def test_channel_for_uses_job_id() -> None:
    assert event_bus.channel_for("abc-123") == "video:abc-123:events"


@dataclass
class _MinimalJob:
    """The subset of columns present on a fresh row from upstream/main. No
    substep_* or attempt_* fields — snapshot_of must still produce a valid
    payload so the SSE stream stays working before #3 / #4 land."""

    id: str
    status: str
    language: str
    batch_id: str | None
    quality_profile: str | None
    production_config: str | None
    progress: int
    current_step: str | None
    error_message: str | None


def test_snapshot_of_survives_missing_optional_columns() -> None:
    job = _MinimalJob(
        id="job-1",
        status="planning",
        language="fr",
        batch_id=None,
        quality_profile="standard",
        production_config='{"render_engine": "manim", "mode": "technical"}',
        progress=5,
        current_step="planning",
        error_message=None,
    )
    snap = event_bus.snapshot_of(job)  # type: ignore[arg-type]
    assert snap["job_id"] == "job-1"
    assert snap["status"] == "planning"
    assert snap["render_engine"] == "manim"
    assert snap["production_mode"] == "technical"
    assert snap["substep"] is None
    assert snap["attempt_number"] is None
    assert snap["max_attempts"] is None
    assert snap["last_repair_reason"] is None
    # Payload must be JSON-serialisable — the publisher relies on it.
    json.dumps(snap)


@dataclass
class _RichJob(_MinimalJob):
    """A row that also has the columns from #3 and #4; the snapshot picks
    them up when present."""

    attempt_number: int = 0
    max_attempts: int = 1
    last_repair_reason: str | None = None
    substep_unit: str | None = None
    substep_current: int | None = None
    substep_total: int | None = None
    substep_eta_seconds: int | None = None


def test_snapshot_of_includes_substep_when_populated() -> None:
    job = _RichJob(
        id="job-2",
        status="render_final",
        language="en",
        batch_id=None,
        quality_profile="standard",
        production_config="{}",
        progress=55,
        current_step="render_final",
        error_message=None,
        substep_unit="frames",
        substep_current=1234,
        substep_total=4429,
        substep_eta_seconds=180,
    )
    snap = event_bus.snapshot_of(job)  # type: ignore[arg-type]
    assert snap["substep"] == {
        "unit": "frames",
        "current": 1234,
        "total": 4429,
        "eta_seconds": 180,
    }


def test_snapshot_of_omits_substep_when_incomplete() -> None:
    """The triplet must be complete for the substep to show up — a partial
    row (say, mid-write during a race) mustn't leak nulls into the payload."""
    job = _RichJob(
        id="job-3",
        status="render_final",
        language="en",
        batch_id=None,
        quality_profile=None,
        production_config=None,
        progress=55,
        current_step="render_final",
        error_message=None,
        substep_unit="frames",
        substep_current=None,  # missing
        substep_total=4429,
    )
    assert event_bus.snapshot_of(job)["substep"] is None  # type: ignore[arg-type]


def test_snapshot_of_tolerates_bad_production_json() -> None:
    """Callers store arbitrary text there; a corrupt row shouldn't crash the
    publisher."""
    job = _MinimalJob(
        id="job-4",
        status="planning",
        language="fr",
        batch_id=None,
        quality_profile=None,
        production_config="not-json-at-all",
        progress=5,
        current_step="planning",
        error_message=None,
    )
    snap = event_bus.snapshot_of(job)  # type: ignore[arg-type]
    assert snap["render_engine"] is None
    assert snap["production_mode"] is None


def test_publish_swallows_redis_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """A Redis outage during a live render must not raise into the pipeline —
    the DB write is authoritative; the event stream is advisory."""

    class _BoomClient:
        def publish(self, *_args, **_kwargs) -> int:
            raise ConnectionError("redis is down")

    monkeypatch.setattr(event_bus, "_publisher", lambda: _BoomClient())
    # No assertion on the return value; the mere absence of an exception is
    # the contract.
    event_bus.publish_job_snapshot(
        _MinimalJob(
            id="job-5",
            status="planning",
            language="fr",
            batch_id=None,
            quality_profile=None,
            production_config=None,
            progress=5,
            current_step="planning",
            error_message=None,
        ),  # type: ignore[arg-type]
    )
