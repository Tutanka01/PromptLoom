from __future__ import annotations

import logging

from video_api.celery_app import celery_app
from video_api.config import get_settings
from video_api.db import SessionLocal, gc_job_workspaces, init_db
from video_api.logging_setup import configure_logging
from video_api.models import VideoJob
from video_api.pipeline.production import VideoPipeline


settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@celery_app.task(name="video_api.run_video_job", bind=True)
def run_video_job(self, job_id: str) -> dict[str, str]:
    logger.info("worker.task.received task_id=%s job_id=%s", self.request.id, job_id)
    init_db()
    pipeline = VideoPipeline()
    status = pipeline.run(job_id)
    logger.info("worker.task.completed task_id=%s job_id=%s status=%s", self.request.id, job_id, status)
    if status == "completed":
        _fan_out_batch(job_id)
    else:
        _abort_batch_secondaries(job_id, status)
    return {"job_id": job_id, "status": status}


def _fan_out_batch(primary_job_id: str) -> None:
    """When a batch's primary job completes, enqueue the secondary-language jobs.

    Each secondary translates the primary's now-validated master blueprint, so we
    only start them once we know the master renders. Idempotent: only secondaries
    still in their initial 'waiting_for_master' state are enqueued, so a retry of
    the primary task can't double-enqueue them."""
    try:
        with SessionLocal() as session:
            primary = session.get(VideoJob, primary_job_id)
            if primary is None or not primary.batch_id or not primary.is_primary:
                return
            secondaries = (
                session.query(VideoJob)
                .filter(
                    VideoJob.batch_id == primary.batch_id,
                    VideoJob.is_primary.is_(False),
                    VideoJob.current_step == "waiting_for_master",
                    VideoJob.status == "queued",
                )
                .all()
            )
            for job in secondaries:
                job.current_step = "queued"
                session.add(job)
            session.commit()
            for job in secondaries:
                result = run_video_job.delay(job.id)
                job.celery_task_id = result.id
                logger.info(
                    "worker.batch.fan_out batch_id=%s job_id=%s language=%s task_id=%s",
                    primary.batch_id,
                    job.id,
                    job.language,
                    result.id,
                )
            session.commit()
            logger.info(
                "worker.batch.fan_out.done batch_id=%s primary_job_id=%s secondaries=%d",
                primary.batch_id,
                primary_job_id,
                len(secondaries),
            )
    except Exception:
        logger.exception("worker.batch.fan_out.error primary_job_id=%s", primary_job_id)


def _abort_batch_secondaries(primary_job_id: str, primary_status: str) -> None:
    """When a batch's primary job does not complete, there is no master blueprint
    to translate, so the still-waiting secondaries can never run. Mark them failed
    with a clear reason instead of leaving them queued until the stale reaper."""
    try:
        with SessionLocal() as session:
            primary = session.get(VideoJob, primary_job_id)
            if primary is None or not primary.batch_id or not primary.is_primary:
                return
            secondaries = (
                session.query(VideoJob)
                .filter(
                    VideoJob.batch_id == primary.batch_id,
                    VideoJob.is_primary.is_(False),
                    VideoJob.current_step == "waiting_for_master",
                    VideoJob.status == "queued",
                )
                .all()
            )
            for job in secondaries:
                job.status = "failed_generation"
                job.current_step = "waiting_for_master"
                job.error_message = (
                    f"primary job {primary_job_id} did not complete (status={primary_status}); "
                    "no master blueprint to translate"
                )
                session.add(job)
            if secondaries:
                session.commit()
                logger.warning(
                    "worker.batch.aborted batch_id=%s primary_status=%s secondaries=%d",
                    primary.batch_id,
                    primary_status,
                    len(secondaries),
                )
    except Exception:
        logger.exception("worker.batch.abort.error primary_job_id=%s", primary_job_id)


@celery_app.task(name="video_api.gc_job_artifacts")
def gc_job_artifacts() -> dict[str, int]:
    """Periodic retention sweep (Celery beat): delete artifact directories of
    terminal jobs older than VIDEO_API_JOB_TTL_DAYS. No-op when retention is
    disabled (ttl <= 0). Idempotent and safe to run alongside the API-startup
    sweep — already-removed workspaces are simply skipped."""
    ttl_days = settings.job_ttl_days
    if ttl_days <= 0:
        return {"collected": 0}
    init_db()
    collected = gc_job_workspaces(settings.jobs_root, ttl_days)
    logger.info("worker.gc.done ttl_days=%g collected=%d", ttl_days, collected)
    return {"collected": collected}
