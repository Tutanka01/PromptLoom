"""Batch TTS jobs: a queue, one GPU worker, per-segment progress.

Consistent-voice anchoring drives the ordering: the first available WAV
(uploaded reference, else the first generated segment) becomes the cloning
reference for every following segment, exactly like the local ``moss`` engine
in ``generate_voice_en.py``. So the anchor is rendered first and alone; once it
exists, all the remaining segments share it and are generated together in
batches of ``TTS_SERVER_BATCH_SIZE`` (1 = strictly sequential).

Job state lives in memory and is mirrored to ``<data>/jobs/<id>/job.json``
after every segment, so polling clients see progress and a restarted server
can still serve completed downloads. Jobs interrupted by a restart are marked
failed (the video worker then retries the whole voice step, which mostly hits
the audio cache).
"""
from __future__ import annotations

import json
import logging
import os
import queue
import shutil
import subprocess
import threading
import time
import uuid
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path

from tts_server.cache import AudioCache
from tts_server.config import Settings
from tts_server.engine import BaseEngine

logger = logging.getLogger(__name__)

REFERENCE_FILE_NAME = "reference.wav"
JOB_FILE_NAME = "job.json"


def wav_duration_seconds(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as handle:
            frames = handle.getnframes()
            rate = handle.getframerate()
        return round(frames / float(rate), 3) if rate else None
    except Exception:  # noqa: BLE001 - duration is informative, not critical
        return None


def encode_mp3(wav_path: Path, mp3_path: Path) -> None:
    """Encode the compatibility MP3 lazily and publish it atomically."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required to encode MP3")
    part_path = mp3_path.with_suffix(f"{mp3_path.suffix}.part")
    part_path.unlink(missing_ok=True)
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-i",
                str(wav_path),
                "-codec:a",
                "libmp3lame",
                "-q:a",
                "2",
                "-f",
                "mp3",
                str(part_path),
            ],
            capture_output=True,
        )
        if result.returncode != 0 or not part_path.exists():
            detail = result.stderr.decode("utf-8", "replace")[-500:]
            raise RuntimeError(f"ffmpeg failed to encode MP3: {detail}")
        os.replace(part_path, mp3_path)
    finally:
        part_path.unlink(missing_ok=True)


@dataclass
class SegmentState:
    key: str
    text: str
    status: str = "pending"  # pending | running | done | failed
    cached: bool = False
    duration_seconds: float | None = None
    error: str | None = None


@dataclass
class Job:
    id: str
    language: str
    consistent_voice: bool
    model_id: str
    created_at: float
    segments: list[SegmentState] = field(default_factory=list)
    status: str = "queued"  # queued | running | completed | failed
    error: str | None = None
    finished_at: float | None = None
    has_reference: bool = False


class JobStore:
    def __init__(self, settings: Settings, engine: BaseEngine, cache: AudioCache) -> None:
        self.settings = settings
        self.engine = engine
        self.cache = cache
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()
        self._queue: queue.Queue[str] = queue.Queue()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self.settings.jobs_dir.mkdir(parents=True, exist_ok=True)

    # -- lifecycle -----------------------------------------------------------
    def start(self) -> None:
        self._recover_interrupted()
        worker = threading.Thread(target=self._worker_loop, name="tts-worker", daemon=True)
        sweeper = threading.Thread(target=self._sweep_loop, name="tts-sweeper", daemon=True)
        worker.start()
        sweeper.start()
        self._threads = [worker, sweeper]

    def stop(self) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=2)

    def _recover_interrupted(self) -> None:
        for job_file in self.settings.jobs_dir.glob(f"*/{JOB_FILE_NAME}"):
            try:
                data = json.loads(job_file.read_text(encoding="utf-8"))
                segments = [SegmentState(**segment) for segment in data.pop("segments", [])]
                job = Job(segments=segments, **data)
            except (TypeError, ValueError, OSError):
                logger.warning("jobs.recover.unreadable file=%s", job_file)
                continue
            if job.status in {"queued", "running"}:
                job.status = "failed"
                job.error = "interrupted by server restart"
                job.finished_at = time.time()
                self._persist(job)
            with self._lock:
                self._jobs[job.id] = job

    # -- public API ----------------------------------------------------------
    def create(
        self,
        *,
        language: str,
        consistent_voice: bool,
        segments: list[tuple[str, str]],
        reference_bytes: bytes | None,
    ) -> Job:
        job = Job(
            id=uuid.uuid4().hex,
            language=language,
            consistent_voice=consistent_voice,
            model_id=self.settings.model_id,
            created_at=time.time(),
            segments=[SegmentState(key=key, text=text) for key, text in segments],
            has_reference=reference_bytes is not None,
        )
        job_dir = self.job_dir(job.id)
        job_dir.mkdir(parents=True, exist_ok=True)
        if reference_bytes:
            (job_dir / REFERENCE_FILE_NAME).write_bytes(reference_bytes)
        with self._lock:
            self._jobs[job.id] = job
        self._persist(job)
        self._queue.put(job.id)
        logger.info(
            "job.created id=%s language=%s segments=%d reference=%s",
            job.id,
            language,
            len(job.segments),
            job.has_reference,
        )
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def job_dir(self, job_id: str) -> Path:
        return self.settings.jobs_dir / job_id

    def queue_depth(self) -> int:
        return self._queue.qsize()

    def public_state(self, job: Job) -> dict:
        segments = []
        for segment in job.segments:
            entry: dict = {
                "key": segment.key,
                "status": segment.status,
                "cached": segment.cached,
                "duration_seconds": segment.duration_seconds,
                "error": segment.error,
            }
            if segment.status == "done":
                entry["wav_url"] = f"/v1/jobs/{job.id}/audio/{segment.key}.wav"
                # Compatibility URL: the MP3 is encoded only when first requested.
                entry["mp3_url"] = f"/v1/jobs/{job.id}/audio/{segment.key}.mp3"
            segments.append(entry)
        return {
            "job_id": job.id,
            "status": job.status,
            "error": job.error,
            "language": job.language,
            "model": job.model_id,
            "consistent_voice": job.consistent_voice,
            "created_at": job.created_at,
            "finished_at": job.finished_at,
            "segments": segments,
        }

    # -- worker --------------------------------------------------------------
    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            try:
                job_id = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            job = self.get(job_id)
            if job is None:
                continue
            try:
                self._process(job)
            except Exception as error:  # noqa: BLE001 - job must fail, not the worker
                logger.exception("job.failed id=%s", job.id)
                job.status = "failed"
                job.error = f"{type(error).__name__}: {error}"
                job.finished_at = time.time()
                self._persist(job)

    def _process(self, job: Job) -> None:
        job.status = "running"
        self._persist(job)
        job_dir = self.job_dir(job.id)
        anchor: Path | None = None
        uploaded_reference = job_dir / REFERENCE_FILE_NAME
        if uploaded_reference.exists():
            anchor = uploaded_reference

        segments = job.segments
        start_index = 0
        # Consistent voice without an uploaded reference: the first segment must
        # be rendered alone because its WAV becomes the cloning anchor for every
        # following segment. Once that anchor exists, all the rest share it and
        # can be generated in one batched pass.
        if job.consistent_voice and anchor is None and segments:
            self._render_segment(job, job_dir, segments[0], anchor)
            anchor = job_dir / f"{segments[0].key}.wav"
            start_index = 1

        self._render_remaining(job, job_dir, segments[start_index:], anchor)

        job.status = "completed"
        job.finished_at = time.time()
        self._persist(job)
        logger.info("job.completed id=%s segments=%d", job.id, len(job.segments))

    def _fingerprint(self, job: Job, text: str, anchor: Path | None) -> str:
        return self.cache.fingerprint(
            model_id=job.model_id,
            language=job.language,
            text=text,
            reference_hash=self.cache.file_hash(anchor),
        )

    def _finalize_segment(self, job: Job, job_dir: Path, segment: SegmentState, out_path: Path) -> None:
        segment.duration_seconds = wav_duration_seconds(out_path)
        segment.status = "done"
        self._persist(job)

    def ensure_mp3(self, job: Job, key: str) -> Path:
        """Return a segment MP3, creating it on demand from the canonical WAV."""
        segment = next((item for item in job.segments if item.key == key), None)
        if segment is None or segment.status != "done":
            raise FileNotFoundError(f"audio not generated yet for {key}")
        job_dir = self.job_dir(job.id)
        wav_path = job_dir / f"{key}.wav"
        mp3_path = job_dir / f"{key}.mp3"
        if not wav_path.exists():
            raise FileNotFoundError(wav_path)
        with self._lock:
            if not mp3_path.exists():
                encode_mp3(wav_path, mp3_path)
        return mp3_path

    def _render_segment(
        self, job: Job, job_dir: Path, segment: SegmentState, anchor: Path | None
    ) -> None:
        segment.status = "running"
        self._persist(job)
        started = time.monotonic()
        out_path = job_dir / f"{segment.key}.wav"
        fingerprint = self._fingerprint(job, segment.text, anchor)
        cached = self.cache.lookup(fingerprint)
        if cached is not None:
            shutil.copyfile(cached, out_path)
            segment.cached = True
        else:
            self.engine.synthesize(segment.text, job.language, anchor, out_path)
            self.cache.store(fingerprint, out_path)
        self._finalize_segment(job, job_dir, segment, out_path)
        logger.info(
            "job.segment.done id=%s key=%s cached=%s seconds=%.1f",
            job.id,
            segment.key,
            segment.cached,
            time.monotonic() - started,
        )

    def _render_remaining(
        self, job: Job, job_dir: Path, segments: list[SegmentState], anchor: Path | None
    ) -> None:
        # Serve cached segments immediately; only the misses feed the batch.
        pending: list[tuple[SegmentState, Path, str]] = []
        for segment in segments:
            segment.status = "running"
        if segments:
            self._persist(job)
        for segment in segments:
            out_path = job_dir / f"{segment.key}.wav"
            fingerprint = self._fingerprint(job, segment.text, anchor)
            cached = self.cache.lookup(fingerprint)
            if cached is not None:
                shutil.copyfile(cached, out_path)
                segment.cached = True
                self._finalize_segment(job, job_dir, segment, out_path)
            else:
                pending.append((segment, out_path, fingerprint))

        batch_size = max(1, self.settings.batch_size)
        for start in range(0, len(pending), batch_size):
            chunk = pending[start : start + batch_size]
            started = time.monotonic()
            self.engine.synthesize_batch(
                [segment.text for segment, _, _ in chunk],
                job.language,
                anchor,
                [out_path for _, out_path, _ in chunk],
            )
            for segment, out_path, fingerprint in chunk:
                self.cache.store(fingerprint, out_path)
                self._finalize_segment(job, job_dir, segment, out_path)
            logger.info(
                "job.batch.done id=%s keys=%s size=%d seconds=%.1f",
                job.id,
                ",".join(segment.key for segment, _, _ in chunk),
                len(chunk),
                time.monotonic() - started,
            )

    def _persist(self, job: Job) -> None:
        job_dir = self.job_dir(job.id)
        job_dir.mkdir(parents=True, exist_ok=True)
        payload = asdict(job)
        (job_dir / JOB_FILE_NAME).write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )

    # -- retention -----------------------------------------------------------
    def _sweep_loop(self) -> None:
        # First sweep shortly after boot, then every 15 minutes.
        while not self._stop.wait(timeout=900):
            try:
                self.sweep()
            except Exception:  # noqa: BLE001 - sweeping must never kill the thread
                logger.exception("jobs.sweep.failed")

    def sweep(self) -> dict[str, int]:
        removed_jobs = 0
        if self.settings.job_ttl_hours > 0:
            cutoff = time.time() - self.settings.job_ttl_hours * 3600
            with self._lock:
                expired = [
                    job.id
                    for job in self._jobs.values()
                    if job.status in {"completed", "failed"}
                    and (job.finished_at or job.created_at) < cutoff
                ]
                for job_id in expired:
                    del self._jobs[job_id]
            for job_id in expired:
                shutil.rmtree(self.job_dir(job_id), ignore_errors=True)
                removed_jobs += 1
        removed_cache = self.cache.prune(self.settings.cache_ttl_days)
        if removed_jobs or removed_cache:
            logger.info("jobs.sweep removed_jobs=%d removed_cache=%d", removed_jobs, removed_cache)
        return {"jobs": removed_jobs, "cache": removed_cache}
