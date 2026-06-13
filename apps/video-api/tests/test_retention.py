"""Artifact retention / garbage collection.

gc_job_workspaces deletes the /data/jobs/<id> directory of terminal jobs older
than the TTL, keeps the DB row (history) and clears its artifact paths. The
periodic Celery task wraps it and no-ops when retention is disabled.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import video_api.tasks as tasks_module
from video_api.config import get_settings
from video_api.db import SessionLocal, gc_job_workspaces, init_db
from video_api.models import VideoJob


@pytest.fixture()
def jobs_root(tmp_path: Path) -> Path:
    init_db()
    # Isolate each test: the in-memory sqlite DB is shared across the process.
    with SessionLocal() as session:
        session.query(VideoJob).delete()
        session.commit()
    return tmp_path / "jobs"


def _make_job(
    jobs_root: Path,
    job_id: str,
    *,
    status: str,
    age_days: float,
    create_dir: bool = True,
) -> Path:
    workspace = jobs_root / job_id
    if create_dir:
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "final.mp4").write_bytes(b"data")
    updated = datetime.now(timezone.utc) - timedelta(days=age_days)
    with SessionLocal() as session:
        session.add(
            VideoJob(
                id=job_id,
                prompt="p",
                status=status,
                artifact_dir=str(workspace),
                final_video_path=str(workspace / "final.mp4"),
                report_path=str(workspace / "report.json"),
                created_at=updated,
                updated_at=updated,
            )
        )
        session.commit()
    return workspace


def test_gc_removes_old_terminal_jobs(jobs_root: Path) -> None:
    old_done = _make_job(jobs_root, "old-done", status="completed", age_days=20)
    old_failed = _make_job(jobs_root, "old-failed", status="failed_quality", age_days=20)
    old_cancelled = _make_job(jobs_root, "old-cancelled", status="cancelled", age_days=20)

    collected = gc_job_workspaces(jobs_root, ttl_days=15)

    assert collected == 3
    assert not old_done.exists()
    assert not old_failed.exists()
    assert not old_cancelled.exists()
    # Row kept, artifact paths cleared so download/report 404 cleanly.
    with SessionLocal() as session:
        row = session.get(VideoJob, "old-done")
        assert row is not None
        assert row.final_video_path is None
        assert row.report_path is None


def test_gc_keeps_recent_and_running_jobs(jobs_root: Path) -> None:
    recent = _make_job(jobs_root, "recent-done", status="completed", age_days=2)
    running_old = _make_job(jobs_root, "running-old", status="running", age_days=30)
    queued_old = _make_job(jobs_root, "queued-old", status="queued", age_days=30)

    collected = gc_job_workspaces(jobs_root, ttl_days=15)

    assert collected == 0
    assert recent.exists()
    assert running_old.exists()  # never collect a job still in flight
    assert queued_old.exists()


def test_gc_skips_workspace_outside_jobs_root(jobs_root: Path, tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere" / "evil"
    outside.mkdir(parents=True)
    (outside / "keep").write_bytes(b"x")
    with SessionLocal() as session:
        updated = datetime.now(timezone.utc) - timedelta(days=30)
        session.add(
            VideoJob(
                id="escapee",
                prompt="p",
                status="completed",
                artifact_dir=str(outside),
                created_at=updated,
                updated_at=updated,
            )
        )
        session.commit()

    collected = gc_job_workspaces(jobs_root, ttl_days=15)

    assert collected == 0
    assert outside.exists()  # path-traversal guard: never delete outside jobs_root


def test_gc_task_noops_when_retention_disabled(jobs_root: Path, monkeypatch) -> None:
    old = _make_job(jobs_root, "old-done", status="completed", age_days=30)
    disabled = dataclasses.replace(get_settings(), job_ttl_days=0, jobs_root=jobs_root)
    monkeypatch.setattr(tasks_module, "settings", disabled)

    result = tasks_module.gc_job_artifacts()

    assert result == {"collected": 0}
    assert old.exists()


def test_gc_task_collects_when_enabled(jobs_root: Path, monkeypatch) -> None:
    old = _make_job(jobs_root, "old-done", status="completed", age_days=30)
    enabled = dataclasses.replace(get_settings(), job_ttl_days=15, jobs_root=jobs_root)
    monkeypatch.setattr(tasks_module, "settings", enabled)

    result = tasks_module.gc_job_artifacts()

    assert result == {"collected": 1}
    assert not old.exists()
