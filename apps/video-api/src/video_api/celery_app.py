from __future__ import annotations

from celery import Celery

from video_api.config import get_settings


settings = get_settings()

celery_app = Celery(
    "video_api",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["video_api.tasks"],
)

celery_app.conf.update(
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
