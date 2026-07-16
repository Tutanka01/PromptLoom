"""Redis pub/sub bridge between the worker and the SSE endpoint.

The worker calls ``publish_job_snapshot`` after every state change (status
transition, attempt bump, sub-step tick) with a JSON snapshot of the
`VideoStatusResponse`. The API's SSE handler subscribes to
``video:{job_id}:events`` and forwards each message to the connected client.

Failures are logged and swallowed: a Redis blip must never sink a running
render. Clients that lose the SSE connection fall back to polling.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import redis
from sqlalchemy.orm import Session

from video_api.config import get_settings
from video_api.models import VideoJob


logger = logging.getLogger(__name__)

_CHANNEL_TEMPLATE = "video:{job_id}:events"


def channel_for(job_id: str) -> str:
    return _CHANNEL_TEMPLATE.format(job_id=job_id)


_client: "redis.Redis | None" = None


def _publisher() -> "redis.Redis":
    """Lazy Redis client. One connection per worker process, reused across
    publishes. ``decode_responses=True`` so we receive strings on the
    subscriber side and don't have to fight bytes."""
    global _client
    if _client is None:
        _client = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


def snapshot_of(job: VideoJob) -> dict[str, Any]:
    """Serialise a `VideoJob` row into the same shape as
    ``VideoStatusResponse``. Kept here (and not in ``main.py``) so the worker
    doesn't have to import the FastAPI app just to publish an event.
    Duplication of the field mapping is deliberate: this snapshot only carries
    the columns present on the row (no computed URLs) — the SSE consumer can
    reconstruct the rest from the ``job_id``."""
    try:
        production = json.loads(job.production_config or "{}")
    except (TypeError, ValueError):
        production = {}
    substep = None
    substep_unit = getattr(job, "substep_unit", None)
    substep_current = getattr(job, "substep_current", None)
    substep_total = getattr(job, "substep_total", None)
    if substep_unit and substep_current is not None and substep_total is not None:
        substep = {
            "unit": substep_unit,
            "current": substep_current,
            "total": substep_total,
            "eta_seconds": getattr(job, "substep_eta_seconds", None),
        }
    return {
        "job_id": job.id,
        "status": job.status,
        "language": job.language,
        "batch_id": job.batch_id,
        "quality_profile": job.quality_profile,
        "render_engine": production.get("render_engine"),
        "production_mode": production.get("mode"),
        "progress": job.progress,
        "current_step": job.current_step,
        "error_message": job.error_message,
        "attempt_number": getattr(job, "attempt_number", None),
        "max_attempts": getattr(job, "max_attempts", None),
        "last_repair_reason": getattr(job, "last_repair_reason", None),
        "substep": substep,
    }


def publish_job_snapshot(job: VideoJob) -> None:
    """Publish the current row snapshot to ``video:{job.id}:events``. Called
    from ``VideoPipeline._update`` / ``_set_attempt_state`` and from the
    sub-step reporters, immediately after the DB commit. Silent on failure
    so a Redis outage doesn't sink an in-progress render."""
    try:
        payload = json.dumps(snapshot_of(job), separators=(",", ":"))
        _publisher().publish(channel_for(job.id), payload)
    except Exception:
        logger.exception("event_bus.publish.failed job_id=%s", getattr(job, "id", "?"))


def publish_from_session(session: Session, job_id: str) -> None:
    """Re-read ``job`` from the session and publish. Useful when the caller
    doesn't hold the model in scope (rare — most callers already have it)."""
    job = session.get(VideoJob, job_id)
    if job is None:
        return
    publish_job_snapshot(job)
