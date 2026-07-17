from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from sqlalchemy import text

from sqlalchemy.orm import Session

from video_api.config import get_settings
from video_api.db import SessionLocal, gc_job_workspaces, get_session, init_db, reap_stale_jobs
from video_api.logging_setup import configure_logging
from video_api.models import VideoJob
from video_api.capabilities import capabilities_payload
from video_api.schemas import (
    BatchJobRef,
    BatchStatusResponse,
    CapabilitiesResponse,
    VideoCreateRequest,
    VideoCreateResponse,
    VideoStatusResponse,
    VoicesResponse,
)
from video_api.event_bus import channel_for, snapshot_of
from video_api.storage import ensure_within, job_root
from video_api.tasks import run_video_job
from video_api.voices import VoiceSelectionError, resolve_voice, voices_payload


settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

_TERMINAL_PREFIXES = ("failed",)


def _is_terminal(status: str) -> bool:
    return status == "completed" or status == "cancelled" or status.startswith(_TERMINAL_PREFIXES)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("api.startup app=%s jobs_root=%s", settings.app_name, settings.jobs_root)
    init_db(max_attempts=30, delay_seconds=2.0)
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


def require_api_key_or_query(
    x_api_key: str | None = Header(default=None),
    api_key: str | None = Query(default=None),
) -> None:
    """Same as ``require_api_key`` but also accepts the key via
    ``?api_key=<value>`` in the URL. Meant for endpoints consumed by
    ``EventSource`` — the browser API can't attach a custom header, so a
    query-string fallback is the standard way to authenticate SSE streams.
    Both entry points are equivalent; either matching value passes."""
    if not settings.api_keys:
        return
    if x_api_key in settings.api_keys or api_key in settings.api_keys:
        return
    raise HTTPException(status_code=401, detail="invalid or missing API key")


app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)


def _status_response(job: VideoJob) -> VideoStatusResponse:
    download_url = f"/v1/videos/{job.id}/download" if job.status == "completed" else None
    report_url = f"/v1/videos/{job.id}/report" if job.report_path else None
    try:
        production = json.loads(job.production_config or "{}")
    except (TypeError, ValueError):
        production = {}
    return VideoStatusResponse(
        job_id=job.id,
        status=job.status,
        language=job.language,
        batch_id=job.batch_id,
        progress=job.progress,
        current_step=job.current_step,
        error_message=job.error_message,
        download_url=download_url,
        report_url=report_url,
        quality_profile=job.quality_profile,
        render_engine=production.get("render_engine"),
        production_mode=production.get("mode"),
        attempt_number=job.attempt_number,
        max_attempts=job.max_attempts,
        last_repair_reason=job.last_repair_reason,
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


@app.get(
    "/v1/capabilities",
    response_model=CapabilitiesResponse,
    dependencies=[Depends(require_api_key)],
)
def get_capabilities() -> CapabilitiesResponse:
    """Effective deployment state: which languages the configured TTS engine
    can speak per quality profile, which optional features (research, stock
    media, visual review) are actually configured, plus request limits and
    defaults. Clients should drive their forms from this instead of hardcoding
    what the server may or may not support."""
    return CapabilitiesResponse(**capabilities_payload(settings))


@app.get(
    "/v1/voices",
    response_model=VoicesResponse,
    dependencies=[Depends(require_api_key)],
)
def list_available_voices() -> VoicesResponse:
    """Selectable narration voices for the deployed TTS engine(s).

    Clients should pick from here before POSTing a `voice`: the effective
    engine depends on the quality profile (draft forces Kokoro), and MOSS
    voices are reference WAVs of the server-side voice bank.
    """
    return VoicesResponse(**voices_payload(settings))


@app.post(
    "/v1/videos",
    response_model=VideoCreateResponse,
    status_code=202,
    dependencies=[Depends(require_api_key)],
)
def create_video(request: VideoCreateRequest, session: Session = Depends(get_session)) -> VideoCreateResponse:
    languages = request.resolved_languages()
    if request.voice:
        try:
            resolve_voice(settings, request.quality_profile, request.voice, languages)
        except VoiceSelectionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if len(languages) > 1:
        return _create_batch(request, languages, session)

    job_id = str(uuid4())
    artifact_dir = str(job_root(settings.jobs_root, job_id))
    logger.info(
        "api.job.create_requested job_id=%s language=%s theme=%s profile=%s prompt_chars=%d artifact_dir=%s",
        job_id,
        languages[0],
        request.theme,
        request.quality_profile,
        len(request.prompt),
        artifact_dir,
    )
    production_config = request.production_options().model_dump()
    job = VideoJob(
        id=job_id,
        prompt=request.prompt,
        theme=request.theme,
        language=languages[0],
        target_duration_seconds=request.target_duration_seconds,
        quality_profile=request.quality_profile,
        production_config=json.dumps(production_config),
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


def _create_batch(
    request: VideoCreateRequest, languages: list[str], session: Session
) -> VideoCreateResponse:
    """Create one video per language from a single prompt. The primary language
    (first) generates the master blueprint and is enqueued immediately; the
    secondaries are persisted as queued and enqueued by the worker once the
    primary completes (they translate its master). See tasks.fan_out_batch."""
    batch_id = str(uuid4())
    logger.info(
        "api.batch.create_requested batch_id=%s languages=%s theme=%s profile=%s prompt_chars=%d",
        batch_id,
        ",".join(languages),
        request.theme,
        request.quality_profile,
        len(request.prompt),
    )
    refs: list[BatchJobRef] = []
    primary_id: str | None = None
    for index, language in enumerate(languages):
        job_id = str(uuid4())
        is_primary = index == 0
        if is_primary:
            primary_id = job_id
        production_config = request.production_options().model_dump()
        job = VideoJob(
            id=job_id,
            prompt=request.prompt,
            theme=request.theme,
            language=language,
            batch_id=batch_id,
            is_primary=is_primary,
            target_duration_seconds=request.target_duration_seconds,
            quality_profile=request.quality_profile,
            production_config=json.dumps(production_config),
            callback_url=request.callback_url,
            status="queued",
            progress=0,
            current_step="queued" if is_primary else "waiting_for_master",
            artifact_dir=str(job_root(settings.jobs_root, job_id)),
        )
        session.add(job)
        refs.append(
            BatchJobRef(
                job_id=job_id,
                language=language,
                is_primary=is_primary,
                status_url=f"/v1/videos/{job_id}",
            )
        )
    session.commit()

    # Only the primary runs now; secondaries are fanned out by the worker after
    # the master blueprint exists.
    assert primary_id is not None
    result = run_video_job.delay(primary_id)
    primary = session.get(VideoJob, primary_id)
    if primary is not None:
        primary.celery_task_id = result.id
        session.commit()
    logger.info(
        "api.batch.enqueued batch_id=%s primary_job_id=%s task_id=%s secondaries=%d",
        batch_id,
        primary_id,
        result.id,
        len(languages) - 1,
    )
    return VideoCreateResponse(
        job_id=primary_id,
        status_url=f"/v1/videos/{primary_id}",
        batch_id=batch_id,
        jobs=refs,
    )


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


@app.get(
    "/v1/batches/{batch_id}",
    response_model=BatchStatusResponse,
    dependencies=[Depends(require_api_key)],
)
def get_batch(batch_id: str, session: Session = Depends(get_session)) -> BatchStatusResponse:
    jobs = (
        session.query(VideoJob)
        .filter(VideoJob.batch_id == batch_id)
        .order_by(VideoJob.is_primary.desc(), VideoJob.created_at.asc())
        .all()
    )
    if not jobs:
        raise HTTPException(status_code=404, detail="batch not found")
    return BatchStatusResponse(
        batch_id=batch_id,
        languages=[job.language for job in jobs],
        jobs=[_status_response(job) for job in jobs],
    )


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


_SSE_HEARTBEAT_SECONDS = 15.0
_SSE_POLL_TIMEOUT_SECONDS = 1.0


def _is_terminal_snapshot(payload: dict) -> bool:
    status = payload.get("status") or ""
    return status in ("completed", "cancelled") or status.startswith("failed")


@app.get(
    "/v1/videos/{job_id}/events",
    dependencies=[Depends(require_api_key_or_query)],
    response_class=StreamingResponse,
)
async def video_events(job_id: str) -> StreamingResponse:
    """Server-Sent Events stream for one job.

    Contract:

    * The first message is an `event: snapshot` carrying the current row
      state — clients that connect mid-job pick up immediately without an
      extra GET.
    * Every subsequent state change (status transition, attempt bump, sub-step
      tick — see ``event_bus.publish_job_snapshot``) becomes an
      `event: state`.
    * When the job reaches a terminal status the server emits a final
      `event: terminal` and closes.
    * A `: heartbeat` comment is sent every 15 seconds if nothing else moves,
      so proxies don't drop the connection and browsers don't reconnect.

    Failures (Redis outage, job vanished mid-stream) close the response with
    a best-effort `event: error`. Clients that lose the stream fall back to
    polling ``GET /v1/videos/{id}`` — the DB row is authoritative.
    """
    # Cheap existence check so 404 is fast (bad job id doesn't tie up a Redis
    # subscription). We don't hold the session open for the whole stream.
    with SessionLocal() as session:
        job = session.get(VideoJob, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        initial_payload = json.dumps(snapshot_of(job), separators=(",", ":"))
        initial_terminal = _is_terminal(job.status)

    async def stream():
        # Deferred import so the module remains importable without redis
        # installed (tests can then patch and exercise everything else).
        import asyncio
        import time as _time
        import redis.asyncio as aioredis

        yield f"event: snapshot\ndata: {initial_payload}\n\n"

        if initial_terminal:
            # Nothing more will happen — close cleanly.
            yield f"event: terminal\ndata: {initial_payload}\n\n"
            return

        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        pubsub = client.pubsub()
        try:
            await pubsub.subscribe(channel_for(job_id))
        except Exception as exc:
            logger.exception("sse.subscribe.failed job_id=%s", job_id)
            yield f'event: error\ndata: {{"detail": "subscribe failed: {exc.__class__.__name__}"}}\n\n'
            await client.aclose()
            return

        last_heartbeat = _time.monotonic()
        try:
            while True:
                try:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=_SSE_POLL_TIMEOUT_SECONDS,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("sse.get_message.failed job_id=%s", job_id)
                    break

                if message is not None:
                    raw = message.get("data")
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8", errors="replace")
                    if raw:
                        yield f"event: state\ndata: {raw}\n\n"
                        last_heartbeat = _time.monotonic()
                        try:
                            parsed = json.loads(raw)
                            if _is_terminal_snapshot(parsed):
                                yield f"event: terminal\ndata: {raw}\n\n"
                                break
                        except json.JSONDecodeError:
                            # Malformed publisher payload — keep the stream
                            # alive; the DB is the fallback.
                            logger.warning("sse.bad_payload job_id=%s", job_id)
                    continue

                now = _time.monotonic()
                if now - last_heartbeat >= _SSE_HEARTBEAT_SECONDS:
                    # SSE comment lines start with ':' and are ignored by
                    # clients; used purely to keep the TCP connection open.
                    yield ": heartbeat\n\n"
                    last_heartbeat = now
        finally:
            try:
                await pubsub.unsubscribe(channel_for(job_id))
                await pubsub.aclose()
            except Exception:
                pass
            try:
                await client.aclose()
            except Exception:
                pass

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            # Disable proxy buffering (nginx) so events flush immediately.
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


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
    # The pipeline always writes "<slug>-en-final.mp4"; surface the real spoken
    # language in the download name so a batch's files don't all collide.
    download_name = path.name
    if job.language and job.language != "en":
        download_name = path.name.replace("-en-final", f"-{job.language}-final", 1)
    return FileResponse(path, media_type="video/mp4", filename=download_name)


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
