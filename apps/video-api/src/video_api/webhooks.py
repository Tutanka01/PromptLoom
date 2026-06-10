"""Outbound webhook delivery for job terminal states.

POSTs a JSON payload to the job's ``callback_url`` when it completes or fails.
Best-effort: 3 attempts with backoff, 10s timeout, never raises into the
pipeline (a dead callback endpoint must not fail a finished video). Payloads
are signed with HMAC-SHA256 (``X-Video-API-Signature``) when
``VIDEO_API_WEBHOOK_SECRET`` is set.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time

from video_api.config import Settings
from video_api.models import VideoJob

logger = logging.getLogger(__name__)

_ATTEMPTS = 3
_TIMEOUT_SECONDS = 10.0
_BACKOFF_SECONDS = (0.0, 2.0, 8.0)


def job_payload(job: VideoJob) -> dict:
    return {
        "job_id": job.id,
        "status": job.status,
        "progress": job.progress,
        "current_step": job.current_step,
        "error_message": job.error_message,
        "status_url": f"/v1/videos/{job.id}",
        "download_url": f"/v1/videos/{job.id}/download" if job.status == "completed" else None,
        "report_url": f"/v1/videos/{job.id}/report" if job.report_path else None,
    }


def notify_job_terminal(job: VideoJob, settings: Settings) -> bool:
    """Deliver the terminal-state webhook. Returns True on success, never raises."""
    url = (job.callback_url or "").strip()
    if not url:
        return False
    if not url.startswith(("http://", "https://")):
        logger.warning("webhook.invalid_url job_id=%s url=%s", job.id, url[:120])
        return False

    body = json.dumps(job_payload(job), ensure_ascii=True).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if settings.webhook_secret:
        signature = hmac.new(settings.webhook_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        headers["X-Video-API-Signature"] = f"sha256={signature}"

    import httpx  # pulled in by the openai dependency

    for attempt, backoff in zip(range(_ATTEMPTS), _BACKOFF_SECONDS):
        if backoff:
            time.sleep(backoff)
        try:
            response = httpx.post(url, content=body, headers=headers, timeout=_TIMEOUT_SECONDS)
            if response.status_code < 300:
                logger.info(
                    "webhook.delivered job_id=%s status=%s http=%d attempt=%d",
                    job.id, job.status, response.status_code, attempt,
                )
                return True
            logger.warning(
                "webhook.rejected job_id=%s http=%d attempt=%d", job.id, response.status_code, attempt
            )
        except Exception as exc:
            logger.warning("webhook.attempt_failed job_id=%s attempt=%d error=%s", job.id, attempt, exc)
    logger.error("webhook.gave_up job_id=%s url=%s after %d attempts", job.id, url[:120], _ATTEMPTS)
    return False
