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
    # Bound a runaway job: the soft limit raises SoftTimeLimitExceeded inside the
    # pipeline (which fails the job cleanly in DB); the hard limit kills the
    # process 5 minutes later if the soft one was swallowed.
    task_soft_time_limit=settings.task_time_limit_seconds,
    task_time_limit=settings.task_time_limit_seconds + 300,
)

# Retention sweep: a periodic Celery beat task deletes artifact directories of
# terminal jobs older than VIDEO_API_JOB_TTL_DAYS, so the limit is enforced even
# on a server that never restarts (the API-startup sweep alone would not). Beat
# runs embedded in the worker (`celery worker --beat`, see compose.yaml). When
# retention is disabled (ttl <= 0) the task itself is a cheap no-op; scheduling
# it unconditionally keeps the cadence configurable purely via env.
if settings.gc_interval_hours > 0:
    celery_app.conf.beat_schedule = {
        "gc-job-artifacts": {
            "task": "video_api.gc_job_artifacts",
            "schedule": settings.gc_interval_hours * 3600.0,
        }
    }
