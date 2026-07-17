"""Render/review/verify ordering in VideoPipeline._run_with_repairs.

The visual review moved onto the FINAL assembled MP4 (the file that ships): there
is no longer a low-quality proxy render. These tests drive the orchestration with
a mocked engine so they assert the step order and the review target, not real
rendering.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any
from unittest.mock import MagicMock

import pytest

import video_api.pipeline.production as production
from video_api.config import Settings
from video_api.db import SessionLocal, init_db
from video_api.models import VideoJob
from video_api.pipeline.llm import fake_blueprint
from video_api.pipeline.production import VideoPipeline, VisualReviewError
from video_api.schemas import ProductionOptions, VisualReviewResult


class _FakeRunner:
    """Records commands; the render step also creates the final MP4 on disk."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(
        self,
        args: list[str],
        cwd: Path,
        log_name: str,
        env: Any = None,
        on_line: Any = None,
    ) -> CompletedProcess:
        self.calls.append(args)
        return CompletedProcess(args, 0, stdout="", stderr="")


def _motion_plan() -> dict:
    return {
        "score": 90.0,
        "minimum_score": 60.0,
        "score_passed": True,
        "passed": True,
        "blocking_issues": [],
        "warnings": [],
        "component_mix": {},
    }


def _review_result(passed: bool) -> VisualReviewResult:
    return VisualReviewResult(
        score=90.0 if passed else 40.0,
        passed=passed,
        scene_scores=[],
        issues=[],
        summary="",
    )


def _pipeline(tmp_path: Path, monkeypatch, *, review_passes: bool, max_repairs: int, job_id: str) -> tuple[VideoPipeline, _FakeRunner, str, MagicMock]:
    init_db()
    settings = dataclasses.replace(
        Settings(),
        jobs_root=str(tmp_path / "jobs"),
        fake_llm=False,          # review_enabled requires fake_llm False
        visual_review_enabled=True,
        align_enabled=False,     # manim engine: alignment stage is "skipped"
        max_repair_attempts=max_repairs,
    )
    pipeline = VideoPipeline(settings)
    pipeline.production_options = ProductionOptions()  # mode="technical"

    blueprint = fake_blueprint("Explain derivatives", "math")
    video_dir = tmp_path / "video"
    (video_dir / "final").mkdir(parents=True)

    engine = MagicMock()
    engine.name = "manim"
    engine.output_fps = 30
    engine.generate_blueprint.return_value = blueprint
    engine.materialize.return_value = video_dir
    pipeline.engine = engine

    reviewer = MagicMock()

    def _review(blueprint_arg, video_path, runner_arg, report_dir):
        # The real reviewer creates <report_dir>/vision when extracting frames;
        # mirror that so the report dir exists just as in production.
        (report_dir / "vision").mkdir(parents=True, exist_ok=True)
        return _review_result(review_passes)

    reviewer.review.side_effect = _review
    pipeline.visual_reviewer = reviewer

    monkeypatch.setattr(production, "voice_command_for_settings", lambda s: (["true"], None))
    monkeypatch.setattr(production, "write_editorial_artifacts", lambda *a, **k: _motion_plan())
    monkeypatch.setattr(production, "verify_mp4", lambda *a, **k: {"quality_warnings": []})
    monkeypatch.setattr(
        "video_api.pipeline.editorial.evaluate_rendered_delivery",
        lambda *a, **k: {"passed": True},
    )

    with SessionLocal() as session:
        session.add(
            VideoJob(
                id=job_id, prompt="p", language="en", status="queued",
                progress=0, current_step="queued", artifact_dir=str(tmp_path / "jobs" / job_id),
            )
        )
        session.commit()
    return pipeline, _FakeRunner(), job_id, reviewer


def test_review_runs_on_final_render_when_it_passes(tmp_path: Path, monkeypatch) -> None:
    pipeline, runner, job_id, reviewer = _pipeline(
        tmp_path, monkeypatch, review_passes=True, max_repairs=0, job_id="job-flow-pass"
    )
    workspace = Path(pipeline.settings.jobs_root) / job_id
    workspace.mkdir(parents=True, exist_ok=True)
    reports_dir = workspace / "reports"

    with SessionLocal() as session:
        job = session.get(VideoJob, job_id)
        pipeline._run_with_repairs(session, job, workspace, runner, reports_dir)
        assert job.status == "completed"

    steps = [step for step, _ in pipeline._step_marks]
    # New order: render/assemble the final, THEN review it, THEN verify it.
    assert steps.index("render_final") < steps.index("assemble_final") < steps.index("visual_review")
    assert steps.index("visual_review") < steps.index("verify_final")
    # The proxy render stages are gone entirely.
    assert "render_low_quality" not in steps
    assert "assemble_low_quality" not in steps
    assert "verify_low_quality" not in steps

    # Review inspected the FINAL assembled MP4 with the review report dir.
    call = reviewer.review.call_args
    reviewed_path = call.args[1]
    assert reviewed_path.name.endswith("-en-final.mp4")
    assert reviewed_path.parent.name == "final"
    assert call.args[3] == reports_dir / "review"
    assert (reports_dir / "visual_review.json").exists()


def test_failing_review_raises_after_render_final(tmp_path: Path, monkeypatch) -> None:
    pipeline, runner, job_id, reviewer = _pipeline(
        tmp_path, monkeypatch, review_passes=False, max_repairs=0, job_id="job-flow-fail"
    )
    workspace = Path(pipeline.settings.jobs_root) / job_id
    workspace.mkdir(parents=True, exist_ok=True)
    reports_dir = workspace / "reports"

    with SessionLocal() as session:
        job = session.get(VideoJob, job_id)
        with pytest.raises(VisualReviewError):
            pipeline._run_with_repairs(session, job, workspace, runner, reports_dir)

    steps = [step for step, _ in pipeline._step_marks]
    # The rejected video was already fully rendered — proving the review gates the
    # real deliverable, not a proxy. verify_final never ran on the rejected file.
    assert "render_final" in steps
    assert "assemble_final" in steps
    assert steps[-1] == "visual_review"
    assert "verify_final" not in steps
