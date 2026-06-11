from __future__ import annotations

import json
import logging
import time
import traceback
import dataclasses
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from video_api import timing
from video_api.config import (
    Settings,
    apply_quality_profile,
    get_settings,
    render_quality_for_profile,
    strict_final_verify_for_profile,
)
from video_api.db import SessionLocal
from video_api.models import VideoJob
from video_api.pipeline.commands import CommandRunner
from video_api.pipeline.engine import make_engine
from video_api.pipeline.llm import LLMClient
from video_api.pipeline.verify import verify_mp4
from video_api.pipeline.visual_review import VisualReviewer
from video_api.pipeline.voice import voice_command_for_settings
from video_api.schemas import VisualReviewResult
from video_api.storage import job_root


logger = logging.getLogger(__name__)

__all__ = ["VideoPipeline", "VisualReviewError", "voice_command_for_settings"]


class VisualReviewError(Exception):
    """Raised when the visual review score is below the required threshold."""

    def __init__(self, result: VisualReviewResult) -> None:
        self.result = result
        super().__init__(result.repair_hint())


class JobCancelled(Exception):
    """Raised between steps when the API marked the job cancelled."""


class VideoPipeline:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.llm = LLMClient(self.settings)
        self.engine = make_engine(self.settings, self.llm)
        self.visual_reviewer = VisualReviewer(self.settings)
        self.quality_profile = "standard"
        # (step, monotonic_seconds) marks recorded by _update; turned into the
        # per-step timing table of report.json at completion.
        self._step_marks: list[tuple[str, float]] = []

    def _apply_profile(self, profile: str | None) -> None:
        """Rebuild the per-job components with profile overrides applied."""
        resolved = (profile or "standard").strip().lower()
        if resolved == "final":
            resolved = "standard"
        self.quality_profile = resolved
        adjusted = apply_quality_profile(self.settings, resolved)
        if adjusted is not self.settings:
            self.settings = adjusted
            self.llm = LLMClient(adjusted)
            self.engine = make_engine(adjusted, self.llm)
            self.visual_reviewer = VisualReviewer(adjusted)

    def _update(
        self,
        session: Session,
        job: VideoJob,
        status: str,
        progress: int,
        step: str,
        error: str | None = None,
    ) -> None:
        # Cooperative cancellation: the API flips the DB status to "cancelled";
        # the worker notices at the next step boundary and aborts instead of
        # overwriting it. (Long-running sub-commands still finish their step.)
        fresh_status = session.execute(
            select(VideoJob.status).where(VideoJob.id == job.id)
        ).scalar_one_or_none()
        if fresh_status == "cancelled":
            session.rollback()
            raise JobCancelled()
        job.status = status
        job.progress = progress
        job.current_step = step
        job.error_message = error
        session.add(job)
        session.commit()
        self._step_marks.append((step, time.monotonic()))
        if error:
            logger.error(
                "job.state job_id=%s status=%s progress=%s step=%s error=%s",
                job.id,
                status,
                progress,
                step,
                error,
            )
        else:
            logger.info(
                "job.state job_id=%s status=%s progress=%s step=%s",
                job.id,
                status,
                progress,
                step,
            )

    def _notify_terminal(self, session: Session, job: VideoJob) -> None:
        """Best-effort terminal webhook; never raises into the pipeline."""
        try:
            from video_api.webhooks import notify_job_terminal

            session.refresh(job)
            notify_job_terminal(job, self.settings)
        except Exception:
            logger.exception("job.webhook.error job_id=%s", job.id)

    def _assemble_env(self) -> dict[str, str] | None:
        if not self.settings.music_file:
            return None
        return {
            "MUSIC_FILE": self.settings.music_file,
            "MUSIC_DB": f"{self.settings.music_gain_db:g}",
        }

    def run(self, job_id: str) -> str:
        with SessionLocal() as session:
            job = session.get(VideoJob, job_id)
            if job is None:
                raise RuntimeError(f"job not found: {job_id}")
            self._apply_profile(getattr(job, "quality_profile", None))
            self.settings = dataclasses.replace(self.settings, voice_language=job.language or "en")
            self.llm = LLMClient(self.settings)
            self.engine = make_engine(self.settings, self.llm)
            self.visual_reviewer = VisualReviewer(self.settings)
            workspace = job_root(self.settings.jobs_root, job_id)
            workspace.mkdir(parents=True, exist_ok=True)
            logs_dir = workspace / "logs"
            reports_dir = workspace / "reports"
            runner = CommandRunner(logs_dir, self.settings.command_timeout_seconds)
            logger.info(
                "job.start job_id=%s workspace=%s prompt_chars=%d max_repair_attempts=%d",
                job_id,
                workspace,
                len(job.prompt),
                self.settings.max_repair_attempts,
            )

            try:
                self._run_with_repairs(session, job, workspace, runner, reports_dir)
                self._notify_terminal(session, job)
                return job.status
            except JobCancelled:
                logger.info("job.cancelled job_id=%s step=%s", job_id, job.current_step)
                self._notify_terminal(session, job)
                return "cancelled"
            except Exception as exc:
                current_step = job.current_step or ""
                if current_step == "visual_review":
                    failure_status = "failed_visual_review"
                elif "verify" in current_step:
                    failure_status = "failed_quality"
                elif current_step in {"planning", "materializing_sources", "static_validation"} or current_step.startswith("repairing"):
                    failure_status = "failed_generation"
                else:
                    failure_status = "failed_render"
                error_report = workspace / "error.json"
                error_report.write_text(
                    json.dumps(
                        {
                            "error": str(exc),
                            "traceback": traceback.format_exc(),
                            "current_step": job.current_step,
                        },
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                job.report_path = str(error_report)
                logger.exception(
                    "job.failed job_id=%s status=%s step=%s report=%s",
                    job_id,
                    failure_status,
                    job.current_step,
                    error_report,
                )
                self._update(session, job, failure_status, job.progress, job.current_step or "failed", str(exc))
                self._notify_terminal(session, job)
                return failure_status

    def _run_with_repairs(
        self,
        session: Session,
        job: VideoJob,
        workspace: Path,
        runner: CommandRunner,
        reports_dir: Path,
    ) -> None:
        last_error: Exception | None = None
        blueprint_data: dict | None = None
        for attempt in range(self.settings.max_repair_attempts + 1):
            try:
                logger.info(
                    "job.attempt.start job_id=%s attempt=%d max_attempts=%d",
                    job.id,
                    attempt,
                    self.settings.max_repair_attempts,
                )
                if attempt == 0:
                    self._update(session, job, "planning", 5, "planning")
                    blueprint = self.engine.generate_blueprint(
                        job.prompt,
                        job.theme,
                        job.target_duration_seconds,
                        job.language,
                    )
                else:
                    self._update(session, job, "repairing", 45, f"repairing_attempt_{attempt}")
                    blueprint = None
                    if isinstance(last_error, VisualReviewError):
                        repair_hint = last_error.result.repair_hint()
                        # Scene-level repair first: rewrite only the flagged
                        # scenes so clean scenes keep their narration (and their
                        # cached WAVs). Falls back to the global blueprint
                        # repair when nothing is attributable.
                        repair_scenes = getattr(self.engine, "repair_scenes", None)
                        if repair_scenes is not None and blueprint_data:
                            try:
                                blueprint = repair_scenes(blueprint_data, last_error.result)
                                if blueprint is not None:
                                    logger.info("job.repair.scene_level job_id=%s", job.id)
                            except Exception as repair_exc:
                                logger.warning(
                                    "job.repair.scene_level_failed job_id=%s error=%s — falling back",
                                    job.id,
                                    repair_exc,
                                )
                                blueprint = None
                    else:
                        repair_hint = f"{type(last_error).__name__}: {last_error}"
                    if blueprint is None:
                        blueprint = self.engine.repair_blueprint(
                            job.prompt,
                            blueprint_data or {},
                            repair_hint,
                            job.language,
                        )
                blueprint_data = blueprint.model_dump()
                (workspace / "blueprint.json").write_text(
                    json.dumps(blueprint_data, indent=2) + "\n",
                    encoding="utf-8",
                )
                logger.info(
                    "job.blueprint.ready job_id=%s attempt=%d title=%s slug=%s scenes=%d",
                    job.id,
                    attempt,
                    blueprint.title,
                    blueprint.slug,
                    len(blueprint.scenes),
                )

                self._update(session, job, "generating_sources", 20, "materializing_sources")
                video_dir = self.engine.materialize(blueprint, workspace)
                logger.info(
                    "job.sources.materialized job_id=%s engine=%s video_dir=%s",
                    job.id,
                    self.engine.name,
                    video_dir,
                )

                self._update(session, job, "generating_sources", 26, "scene_codegen")
                self.engine.generate_scenes(blueprint, video_dir)

                self._update(session, job, "static_validation", 30, "static_validation")
                self.engine.validate_static(video_dir)
                logger.info("job.static_validation.done job_id=%s video_dir=%s", job.id, video_dir)

                self._update(session, job, "voice_generation", 40, "voice_generation")
                voice_args, voice_env = voice_command_for_settings(self.settings)
                logger.info(
                    "job.voice.start job_id=%s engine=%s model=%s",
                    job.id,
                    self.settings.voice_engine,
                    self.settings.openai_tts_model
                    if self.settings.voice_engine.strip().lower() == "openai"
                    else self.settings.moss_tts_model
                    if self.settings.voice_engine.strip().lower() in {"moss", "moss-tts", "moss_tts"}
                    else "",
                )
                runner.run(voice_args, cwd=video_dir, log_name="voice.log", env=voice_env)
                logger.info("job.voice.done job_id=%s engine=%s", job.id, self.settings.voice_engine)

                cued_scenes = 0
                if self.engine.name == "remotion" and self.settings.align_enabled:
                    self._update(session, job, "audio_alignment", 44, "audio_alignment")
                    try:
                        from video_api.pipeline.align import align_segments
                        from video_api.pipeline.beats import resolve_cues

                        align_segments(video_dir, device=self.settings.align_device)
                        cued = resolve_cues(video_dir, blueprint)
                        cued_scenes = len(cued)
                        logger.info(
                            "job.align.done job_id=%s scenes_with_cues=%d", job.id, len(cued)
                        )
                    except Exception as align_exc:
                        # Non-fatal: scenes keep their default item timings.
                        logger.warning(
                            "job.align.failed job_id=%s error=%s (continuing without cues)",
                            job.id,
                            align_exc,
                        )

                requested_target = job.target_duration_seconds or self.settings.default_target_duration_seconds
                minimum_duration = _minimum_final_duration(
                    requested_target,
                    self.settings.default_min_duration_seconds,
                )

                # Render policy: the low-quality render only exists to feed the
                # visual review. With review off, skip straight to the final
                # render (one full render less ~= a third of the job time).
                review_enabled = self.settings.visual_review_enabled and not self.settings.fake_llm
                visual_review_result: VisualReviewResult | None = None
                if review_enabled:
                    self._update(session, job, "render_low_quality", 52, "render_low_quality")
                    runner.run(["./render_en.sh"], cwd=video_dir, log_name="render-low.log", env={"QUALITY": "ql"})
                    logger.info("job.render_low_quality.done job_id=%s", job.id)

                    self._update(session, job, "assemble_low_quality", 62, "assemble_low_quality")
                    runner.run(
                        ["./assemble_en.sh"],
                        cwd=video_dir,
                        log_name="assemble-low.log",
                        env=self._assemble_env(),
                    )
                    logger.info("job.assemble_low_quality.done job_id=%s", job.id)

                    final_low = video_dir / "final" / f"{blueprint.slug}-en-final.mp4"
                    self._update(session, job, "verify_low_quality", 68, "verify_low_quality")
                    verify_mp4(
                        final_low,
                        runner,
                        final_quality=False,
                        report_dir=reports_dir / "low",
                        min_duration_seconds=minimum_duration,
                    )
                    logger.info("job.verify_low_quality.done job_id=%s video=%s", job.id, final_low)

                    self._update(session, job, "visual_review", 72, "visual_review")
                    vr = self.visual_reviewer.review(
                        blueprint,
                        final_low,
                        runner,
                        reports_dir / "low",
                    )
                    visual_review_result = vr
                    vr_path = reports_dir / "visual_review.json"
                    vr_path.write_text(vr.model_dump_json(indent=2) + "\n", encoding="utf-8")
                    logger.info(
                        "job.visual_review.done job_id=%s score=%.1f passed=%s blockers=%d",
                        job.id,
                        vr.score,
                        vr.passed,
                        sum(1 for i in vr.issues if i.severity == "blocker"),
                    )
                    if not vr.passed:
                        raise VisualReviewError(vr)

                self._update(session, job, "render_final", 78, "render_final")
                final_render_quality = render_quality_for_profile(self.quality_profile)
                runner.run(
                    ["./render_en.sh"],
                    cwd=video_dir,
                    log_name="render-final.log",
                    env={"QUALITY": final_render_quality},
                )
                logger.info(
                    "job.render_final.done job_id=%s quality=%s", job.id, final_render_quality
                )

                self._update(session, job, "assemble_final", 88, "assemble_final")
                runner.run(
                    ["./assemble_en.sh"],
                    cwd=video_dir,
                    log_name="assemble-final.log",
                    env=self._assemble_env(),
                )
                logger.info("job.assemble_final.done job_id=%s", job.id)

                final_video = video_dir / "final" / f"{blueprint.slug}-en-final.mp4"
                self._update(session, job, "verify_final", 94, "verify_final")
                final_report = verify_mp4(
                    final_video,
                    runner,
                    final_quality=strict_final_verify_for_profile(self.quality_profile),
                    report_dir=reports_dir / "final",
                    min_duration_seconds=minimum_duration,
                    max_freeze_ratio=self.settings.verify_max_freeze_ratio,
                    freeze_floor_seconds=self.settings.verify_freeze_floor_seconds,
                    max_single_freeze_seconds=self.settings.verify_max_single_freeze_seconds,
                    freeze_fatal=self.settings.verify_freeze_fatal,
                    expected_fps=self.engine.output_fps,
                )
                if visual_review_result is not None:
                    final_report["visual_review"] = json.loads(visual_review_result.model_dump_json())
                final_report["quality"] = _quality_summary(blueprint, video_dir, cued_scenes)
                final_report["quality_profile"] = self.quality_profile
                final_report["timings"] = _timings_from_marks(self._step_marks)
                report_path = reports_dir / "report.json"
                report_path.write_text(json.dumps(final_report, indent=2) + "\n", encoding="utf-8")
                job.final_video_path = str(final_video)
                job.report_path = str(report_path)
                self._update(session, job, "completed", 100, "completed")
                logger.info("job.completed job_id=%s final_video=%s report=%s", job.id, final_video, report_path)
                return
            except Exception as exc:
                # A Celery soft time limit means the whole job is out of budget:
                # retrying the full pipeline would just hit the hard kill. A
                # cancelled job must not be "repaired" either.
                if isinstance(exc, JobCancelled) or type(exc).__name__ == "SoftTimeLimitExceeded":
                    raise
                last_error = exc
                attempt_report = workspace / f"attempt_{attempt}_error.txt"
                attempt_report.write_text(
                    traceback.format_exc(),
                    encoding="utf-8",
                )
                logger.exception(
                    "job.attempt.failed job_id=%s attempt=%d step=%s error=%s report=%s",
                    job.id,
                    attempt,
                    job.current_step,
                    exc,
                    attempt_report,
                )
                if attempt >= self.settings.max_repair_attempts:
                    raise
                logger.info(
                    "job.repair.schedule job_id=%s next_attempt=%d previous_error=%s",
                    job.id,
                    attempt + 1,
                    type(exc).__name__,
                )


def _minimum_final_duration(target_duration_seconds: int, default_min_duration_seconds: int) -> int:
    return timing.minimum_final_duration(target_duration_seconds, default_min_duration_seconds)


def _timings_from_marks(marks: list[tuple[str, float]]) -> dict:
    """Per-step wall time from the _update marks: each step's duration runs from
    its own mark to the next one. Repeated steps (repair attempts) accumulate."""
    durations: dict[str, float] = {}
    for (step, started), (_, ended) in zip(marks, marks[1:]):
        durations[step] = round(durations.get(step, 0.0) + (ended - started), 2)
    total = round(marks[-1][1] - marks[0][1], 2) if len(marks) >= 2 else 0.0
    return {"steps_seconds": durations, "total_seconds": total}


def _quality_summary(blueprint: Any, video_dir: Path, cued_scenes: int) -> dict:
    """Distinguish a clean video from a quietly degraded one in report.json.

    - degradations: placeholder props / failed strict validations recorded
      during blueprint generation (empty on a clean run);
    - scenes_fallback: Custom scenes that fell back to a palette BulletScene
      (scene coder exhausted) — read from scenes_map.json vs the blueprint;
    - cued_scenes: scenes whose visual items are narration-synced.
    """
    summary: dict[str, Any] = {
        "scenes_total": len(blueprint.scenes),
        "degradations": list(getattr(blueprint, "degradations", []) or []),
        "cued_scenes": cued_scenes,
    }
    scenes_map_path = video_dir / "scenes_map.json"
    if scenes_map_path.exists():
        try:
            entries = json.loads(scenes_map_path.read_text(encoding="utf-8"))["scenes"]
            by_key = {entry["key"]: entry for entry in entries}
            fallbacks = [
                scene.key
                for scene in blueprint.scenes
                if getattr(scene, "is_custom", False)
                and not by_key.get(scene.key, {}).get("custom", False)
            ]
            summary["scenes_fallback"] = fallbacks
            summary["scenes_rich"] = len(blueprint.scenes) - len(fallbacks)
        except (KeyError, json.JSONDecodeError, OSError):
            pass
    return summary
