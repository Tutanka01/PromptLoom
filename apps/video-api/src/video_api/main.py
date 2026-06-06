from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from video_api.config import get_settings
from video_api.db import get_session, init_db
from video_api.logging_setup import configure_logging
from video_api.models import VideoJob
from video_api.schemas import VideoCreateRequest, VideoCreateResponse, VideoStatusResponse
from video_api.storage import ensure_within, job_root
from video_api.tasks import run_video_job


settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("api.startup app=%s jobs_root=%s", settings.app_name, settings.jobs_root)
    init_db()
    settings.jobs_root.mkdir(parents=True, exist_ok=True)
    logger.info("api.ready")
    yield
    logger.info("api.shutdown")


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)


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
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/videos", response_model=VideoCreateResponse, status_code=202)
def create_video(request: VideoCreateRequest, session: Session = Depends(get_session)) -> VideoCreateResponse:
    job_id = str(uuid4())
    artifact_dir = str(job_root(settings.jobs_root, job_id))
    logger.info(
        "api.job.create_requested job_id=%s language=%s theme=%s prompt_chars=%d artifact_dir=%s",
        job_id,
        request.language,
        request.theme,
        len(request.prompt),
        artifact_dir,
    )
    job = VideoJob(
        id=job_id,
        prompt=request.prompt,
        theme=request.theme,
        language=request.language,
        target_duration_seconds=request.target_duration_seconds,
        status="queued",
        progress=0,
        current_step="queued",
        artifact_dir=artifact_dir,
    )
    session.add(job)
    session.commit()
    run_video_job.delay(job_id)
    logger.info("api.job.enqueued job_id=%s status_url=/v1/videos/%s", job_id, job_id)
    return VideoCreateResponse(job_id=job_id, status_url=f"/v1/videos/{job_id}")


@app.get("/v1/videos/{job_id}", response_model=VideoStatusResponse)
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


@app.get("/v1/videos/{job_id}/download")
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


@app.get("/v1/videos/{job_id}/report")
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
