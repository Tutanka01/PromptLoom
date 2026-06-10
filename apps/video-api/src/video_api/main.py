from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text

from sqlalchemy.orm import Session

from video_api.config import get_settings
from video_api.db import SessionLocal, gc_job_workspaces, get_session, init_db, reap_stale_jobs
from video_api.logging_setup import configure_logging
from video_api.models import VideoJob
from video_api.schemas import VideoCreateRequest, VideoCreateResponse, VideoStatusResponse
from video_api.storage import ensure_within, job_root
from video_api.tasks import run_video_job


settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

_TERMINAL_PREFIXES = ("failed",)


def _is_terminal(status: str) -> bool:
    return status == "completed" or status == "cancelled" or status.startswith(_TERMINAL_PREFIXES)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("api.startup app=%s jobs_root=%s", settings.app_name, settings.jobs_root)
    init_db()
    settings.jobs_root.mkdir(parents=True, exist_ok=True)
    reaped = reap_stale_jobs(settings.stale_job_hours)
    if reaped:
        logger.warning("api.startup.reaped_stale_jobs count=%d", reaped)
    if settings.job_ttl_days > 0:
        collected = gc_job_workspaces(settings.jobs_root, settings.job_ttl_days)
        if collected:
            logger.info("api.startup.gc_job_workspaces count=%d", collected)
    logger.info("api.ready")
    yield
    logger.info("api.shutdown")


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Optional auth: enforced only when VIDEO_API_KEYS is configured."""
    if settings.api_keys and x_api_key not in settings.api_keys:
        raise HTTPException(status_code=401, detail="invalid or missing API key")


app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)


def _status_response(job: VideoJob) -> VideoStatusResponse:
    download_url = f"/v1/videos/{job.id}/download" if job.status == "completed" else None
    report_url = f"/v1/videos/{job.id}/report" if job.report_path else None
    return VideoStatusResponse(
        job_id=job.id,
        status=job.status,
        progress=job.progress,
        current_step=job.current_step,
        error_message=job.error_message,
        download_url=download_url,
        report_url=report_url,
        quality_profile=job.quality_profile,
    )


@app.get("/healthz")
def healthz() -> JSONResponse:
    checks: dict[str, str] = {}
    healthy = True
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {type(exc).__name__}"
        healthy = False
    try:
        import redis as redis_lib

        redis_lib.Redis.from_url(
            settings.redis_url, socket_connect_timeout=2, socket_timeout=2
        ).ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {type(exc).__name__}"
        healthy = False
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "degraded", "checks": checks},
    )


@app.post(
    "/v1/videos",
    response_model=VideoCreateResponse,
    status_code=202,
    dependencies=[Depends(require_api_key)],
)
def create_video(request: VideoCreateRequest, session: Session = Depends(get_session)) -> VideoCreateResponse:
    job_id = str(uuid4())
    artifact_dir = str(job_root(settings.jobs_root, job_id))
    logger.info(
        "api.job.create_requested job_id=%s language=%s theme=%s profile=%s prompt_chars=%d artifact_dir=%s",
        job_id,
        request.language,
        request.theme,
        request.quality_profile,
        len(request.prompt),
        artifact_dir,
    )
    job = VideoJob(
        id=job_id,
        prompt=request.prompt,
        theme=request.theme,
        language=request.language,
        target_duration_seconds=request.target_duration_seconds,
        quality_profile=request.quality_profile,
        callback_url=request.callback_url,
        status="queued",
        progress=0,
        current_step="queued",
        artifact_dir=artifact_dir,
    )
    session.add(job)
    session.commit()
    result = run_video_job.delay(job_id)
    job.celery_task_id = result.id
    session.commit()
    logger.info("api.job.enqueued job_id=%s task_id=%s status_url=/v1/videos/%s", job_id, result.id, job_id)
    return VideoCreateResponse(job_id=job_id, status_url=f"/v1/videos/{job_id}")


@app.get("/v1/videos", dependencies=[Depends(require_api_key)])
def list_videos(
    status: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> dict:
    query = session.query(VideoJob).order_by(VideoJob.created_at.desc())
    if status:
        query = query.filter(VideoJob.status == status)
    jobs = query.offset(offset).limit(limit).all()
    return {
        "jobs": [_status_response(job).model_dump() for job in jobs],
        "limit": limit,
        "offset": offset,
    }


@app.get("/v1/videos/{job_id}", response_model=VideoStatusResponse, dependencies=[Depends(require_api_key)])
def get_video(job_id: str, session: Session = Depends(get_session)) -> VideoStatusResponse:
    job = session.get(VideoJob, job_id)
    if job is None:
        logger.warning("api.job.status_not_found job_id=%s", job_id)
        raise HTTPException(status_code=404, detail="job not found")
    logger.info(
        "api.job.status job_id=%s status=%s progress=%s step=%s",
        job.id,
        job.status,
        job.progress,
        job.current_step,
    )
    return _status_response(job)


@app.delete("/v1/videos/{job_id}", response_model=VideoStatusResponse, dependencies=[Depends(require_api_key)])
def cancel_video(job_id: str, session: Session = Depends(get_session)) -> VideoStatusResponse:
    """Cancel a queued or running job. The worker aborts cooperatively at the
    next step boundary (a long sub-command still finishes its current step)."""
    job = session.get(VideoJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if _is_terminal(job.status):
        raise HTTPException(status_code=409, detail=f"job is already terminal ({job.status})")
    job.status = "cancelled"
    job.error_message = "cancelled by user"
    session.add(job)
    session.commit()
    if job.celery_task_id:
        try:
            from video_api.celery_app import celery_app

            celery_app.control.revoke(job.celery_task_id)
        except Exception:
            logger.exception("api.job.revoke_failed job_id=%s", job_id)
    logger.info("api.job.cancelled job_id=%s", job_id)
    return _status_response(job)


@app.get("/v1/videos/{job_id}/download", dependencies=[Depends(require_api_key)])
def download_video(job_id: str, session: Session = Depends(get_session)) -> FileResponse:
    job = session.get(VideoJob, job_id)
    if job is None:
        logger.warning("api.job.download_not_found job_id=%s", job_id)
        raise HTTPException(status_code=404, detail="job not found")
    if job.status != "completed" or not job.final_video_path:
        logger.info("api.job.download_not_ready job_id=%s status=%s", job_id, job.status)
        raise HTTPException(status_code=409, detail="video is not ready")
    path = ensure_within(Path(job.final_video_path), settings.jobs_root)
    if not path.exists():
        logger.error("api.job.download_missing_file job_id=%s path=%s", job_id, path)
        raise HTTPException(status_code=404, detail="video artifact missing")
    logger.info("api.job.download job_id=%s path=%s", job_id, path)
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@app.get("/v1/videos/{job_id}/report", dependencies=[Depends(require_api_key)])
def get_report(job_id: str, session: Session = Depends(get_session)) -> FileResponse:
    job = session.get(VideoJob, job_id)
    if job is None:
        logger.warning("api.job.report_not_found job_id=%s", job_id)
        raise HTTPException(status_code=404, detail="job not found")
    if not job.report_path:
        logger.info("api.job.report_not_available job_id=%s status=%s", job_id, job.status)
        raise HTTPException(status_code=404, detail="report not available")
    path = ensure_within(Path(job.report_path), settings.jobs_root)
    if not path.exists():
        logger.error("api.job.report_missing_file job_id=%s path=%s", job_id, path)
        raise HTTPException(status_code=404, detail="report artifact missing")
    logger.info("api.job.report job_id=%s path=%s", job_id, path)
    return FileResponse(path, media_type="application/json", filename=path.name)


@app.get("/v1/videos/{job_id}/artifacts/{artifact_path:path}", dependencies=[Depends(require_api_key)])
def get_artifact(job_id: str, artifact_path: str, session: Session = Depends(get_session)) -> FileResponse:
    """Serve any file from the job workspace (blueprint.json, logs/*, reports/*,
    snapshots, ...) — path-traversal-safe via ensure_within."""
    job = session.get(VideoJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    workspace = Path(job.artifact_dir)
    path = ensure_within(workspace / artifact_path, settings.jobs_root)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    logger.info("api.job.artifact job_id=%s path=%s", job_id, path)
    return FileResponse(path, filename=path.name)
