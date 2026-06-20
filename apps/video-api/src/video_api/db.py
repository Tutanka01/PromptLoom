from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from video_api.config import get_settings
from video_api.models import Base, VideoJob

logger = logging.getLogger(__name__)

settings = get_settings()


def _engine_kwargs(url: str) -> dict:
    # An in-memory sqlite DB lives per-connection: without a shared StaticPool,
    # init_db() would create the tables on one connection and every request
    # would see an empty DB on another. Used by the test environment.
    if url.startswith("sqlite") and ":memory:" in url:
        from sqlalchemy.pool import StaticPool

        return {"poolclass": StaticPool, "connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True}


engine = create_engine(settings.database_url, **_engine_kwargs(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_compat_columns()


def reap_stale_jobs(max_age_hours: float) -> int:
    """Fail jobs whose DB row stopped moving (worker killed/OOM/reboot mid-job).

    With acks_late and no result for the dead process, such jobs would otherwise
    show "running" forever. Called at API startup; never raises (a reaper failure
    must not block the app).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    try:
        with SessionLocal() as session:
            stale = (
                session.query(VideoJob)
                .filter(
                    VideoJob.status != "completed",
                    VideoJob.status.notlike("failed%"),
                    VideoJob.updated_at < cutoff,
                )
                .all()
            )
            for job in stale:
                job.status = "failed_stale"
                job.error_message = (
                    f"job stalled: no progress since {job.updated_at} "
                    f"(> {max_age_hours:g}h); marked failed by the startup reaper"
                )
                session.add(job)
                logger.warning("reaper.job_failed job_id=%s last_step=%s", job.id, job.current_step)
            session.commit()
            return len(stale)
    except Exception:
        logger.exception("reaper.error")
        return 0


def _ensure_compat_columns() -> None:
    inspector = inspect(engine)
    if "video_jobs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("video_jobs")}
    migrations = {
        "target_duration_seconds": "ALTER TABLE video_jobs ADD COLUMN target_duration_seconds INTEGER",
        "quality_profile": "ALTER TABLE video_jobs ADD COLUMN quality_profile VARCHAR(16)",
        "production_config": "ALTER TABLE video_jobs ADD COLUMN production_config TEXT",
        "callback_url": "ALTER TABLE video_jobs ADD COLUMN callback_url TEXT",
        "celery_task_id": "ALTER TABLE video_jobs ADD COLUMN celery_task_id VARCHAR(64)",
        "batch_id": "ALTER TABLE video_jobs ADD COLUMN batch_id VARCHAR(36)",
        "is_primary": "ALTER TABLE video_jobs ADD COLUMN is_primary BOOLEAN NOT NULL DEFAULT TRUE",
    }
    pending = [ddl for column, ddl in migrations.items() if column not in columns]
    if not pending:
        return
    with engine.begin() as connection:
        for ddl in pending:
            connection.execute(text(ddl))


def gc_job_workspaces(jobs_root, ttl_days: float) -> int:
    """Delete the workspace directory of terminal jobs older than *ttl_days*.

    The DB row is kept (history/auditing); its artifact paths are cleared so
    download/report return clean 404s instead of dangling references. Never
    raises (GC must not block startup).
    """
    import shutil
    from pathlib import Path

    cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
    collected = 0
    try:
        jobs_root = Path(jobs_root).resolve()
        with SessionLocal() as session:
            candidates = (
                session.query(VideoJob)
                .filter(VideoJob.updated_at < cutoff)
                .filter(
                    (VideoJob.status == "completed")
                    | (VideoJob.status == "cancelled")
                    | VideoJob.status.like("failed%")
                )
                .all()
            )
            for job in candidates:
                workspace = Path(job.artifact_dir).resolve()
                if jobs_root not in workspace.parents:
                    continue
                if workspace.exists():
                    shutil.rmtree(workspace, ignore_errors=True)
                    collected += 1
                    logger.info("gc.workspace_removed job_id=%s path=%s", job.id, workspace)
                job.final_video_path = None
                job.report_path = None
                session.add(job)
            session.commit()
    except Exception:
        logger.exception("gc.error")
    return collected


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
