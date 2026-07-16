"""Repair-loop metadata is persisted to the video_jobs row so the API/Studio
can surface it (attempt_number, max_attempts, last_repair_reason)."""
from __future__ import annotations

from pathlib import Path

import pytest

from video_api.db import SessionLocal
from video_api.models import VideoJob
from video_api.pipeline.production import VisualReviewError

# Reuse the mocking harness from the flow tests: a MagicMock engine + reviewer
# + fake runner + a fake blueprint. That way we don't have to duplicate 60 lines
# of setup and we cover the exact `_run_with_repairs` path.
from tests.test_pipeline_flow import _pipeline


def test_attempt_tracking_happy_path(tmp_path: Path, monkeypatch) -> None:
    """A job that completes on the first try records attempt_number=0 with the
    ceiling from settings and no repair reason. Absence of a reason must not be
    an empty string — the schema treats None as 'nothing happened'."""
    pipeline, runner, job_id, _reviewer = _pipeline(
        tmp_path, monkeypatch, review_passes=True, max_repairs=2, job_id="job-attempts-ok"
    )
    workspace = Path(pipeline.settings.jobs_root) / job_id
    workspace.mkdir(parents=True, exist_ok=True)
    reports_dir = workspace / "reports"

    with SessionLocal() as session:
        job = session.get(VideoJob, job_id)
        pipeline._run_with_repairs(session, job, workspace, runner, reports_dir)
        assert job.status == "completed"
        assert job.attempt_number == 0
        assert job.max_attempts == 3  # settings.max_repair_attempts (2) + 1
        assert job.last_repair_reason is None


def test_attempt_tracking_after_repair_records_reason(tmp_path: Path, monkeypatch) -> None:
    """When the visual review keeps rejecting the render, the row is updated on
    each retry so the Studio can display 'Réparation 1/1 — VisualReviewError:...'
    right up to the terminal failure."""
    pipeline, runner, job_id, _reviewer = _pipeline(
        tmp_path, monkeypatch, review_passes=False, max_repairs=1, job_id="job-attempts-retry"
    )
    # The shared _pipeline harness only wires up generate_blueprint. The retry
    # path needs repair_scenes/repair_blueprint to return the same blueprint so
    # the retry attempt reaches the visual review again (where it fails again).
    from video_api.pipeline.llm import fake_blueprint

    blueprint = fake_blueprint("Explain derivatives", "math")
    pipeline.engine.repair_scenes = None  # skip scene-level repair, fall through
    pipeline.engine.repair_blueprint.return_value = blueprint

    workspace = Path(pipeline.settings.jobs_root) / job_id
    workspace.mkdir(parents=True, exist_ok=True)
    reports_dir = workspace / "reports"

    with SessionLocal() as session:
        job = session.get(VideoJob, job_id)
        with pytest.raises(VisualReviewError):
            pipeline._run_with_repairs(session, job, workspace, runner, reports_dir)
        # Second attempt reached (attempt_number=1) with the reason captured.
        # max_attempts is (max_repair_attempts + 1) = 2.
        assert job.attempt_number == 1
        assert job.max_attempts == 2
        assert job.last_repair_reason is not None
        assert len(job.last_repair_reason) > 0
