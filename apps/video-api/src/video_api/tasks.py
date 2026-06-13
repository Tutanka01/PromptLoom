from __future__ import annotations

import logging

from video_api.celery_app import celery_app
from video_api.config import get_settings
from video_api.db import gc_job_workspaces, init_db
from video_api.logging_setup import configure_logging
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
    return {"job_id": job_id, "status": status}


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
