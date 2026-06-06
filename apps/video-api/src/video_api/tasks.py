from __future__ import annotations

import logging

from video_api.celery_app import celery_app
from video_api.config import get_settings
from video_api.db import init_db
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
    pipeline.run(job_id)
    logger.info("worker.task.completed task_id=%s job_id=%s", self.request.id, job_id)
    return {"job_id": job_id, "status": "done"}
