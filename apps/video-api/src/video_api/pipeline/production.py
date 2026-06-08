from __future__ import annotations

import ast
import json
import logging
import shlex
import traceback
from pathlib import Path

from sqlalchemy.orm import Session

from video_api import timing
from video_api.config import Settings, get_settings
from video_api.db import SessionLocal
from video_api.models import VideoJob
from video_api.pipeline.commands import CommandRunner
from video_api.pipeline.llm import LLMClient
from video_api.schemas import VideoBlueprint
from video_api.pipeline.materialize import Materializer, build_single_scene_module
from video_api.pipeline.scene_coder import SceneCoder
from video_api.pipeline.validate import (
    smoke_render_scene,
    validate_scene_ast_security,
    validate_scene_names,
    validate_static_video_source,
)
from video_api.pipeline.verify import verify_mp4
from video_api.pipeline.visual_review import VisualReviewer
from video_api.schemas import VisualReviewResult
from video_api.storage import job_root


logger = logging.getLogger(__name__)


def voice_command_for_settings(settings: Settings) -> tuple[list[str], dict[str, str] | None]:
    engine = settings.voice_engine.strip().lower()
    if engine in {"chatterbox", "local", "command"}:
        return shlex.split(settings.voice_command), None
    if engine in {"openai", "openai-compatible", "openai_compatible"}:
        return (
            [
                "python",
                "generate_voice_en.py",
                "--engine",
                "openai",
                "--tail-padding",
                f"{settings.voice_tail_padding:.3f}",
            ],
            {
                "OPENAI_BASE_URL": settings.openai_base_url or "",
                "OPENAI_API_KEY": settings.openai_api_key or "",
                "VIDEO_API_OPENAI_TTS_MODEL": settings.openai_tts_model,
                "VIDEO_API_OPENAI_TTS_VOICE": settings.openai_tts_voice,
                "VIDEO_API_OPENAI_TTS_FORMAT": settings.openai_tts_format,
                "VIDEO_API_OPENAI_TTS_SPEED": str(settings.openai_tts_speed),
            },
        )
    raise ValueError(
        "Unsupported VIDEO_API_VOICE_ENGINE="
        f"{settings.voice_engine!r}; expected 'chatterbox' or 'openai'."
    )


class VisualReviewError(Exception):
    """Raised when the visual review score is below the required threshold."""

    def __init__(self, result: VisualReviewResult) -> None:
        self.result = result
        super().__init__(result.repair_hint())


class VideoPipeline:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.llm = LLMClient(self.settings)
        self.materializer = Materializer(self.settings)
        self.scene_coder = SceneCoder(self.settings)
        self.visual_reviewer = VisualReviewer(self.settings)

    def _update(
        self,
        session: Session,
        job: VideoJob,
        status: str,
        progress: int,
        step: str,
        error: str | None = None,
    ) -> None:
        job.status = status
        job.progress = progress
        job.current_step = step
        job.error_message = error
        session.add(job)
        session.commit()
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

    def run(self, job_id: str) -> str:
        with SessionLocal() as session:
            job = session.get(VideoJob, job_id)
            if job is None:
                raise RuntimeError(f"job not found: {job_id}")
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
                return job.status
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
                    blueprint = self.llm.generate_blueprint(
                        job.prompt,
                        job.theme,
                        job.target_duration_seconds,
                    )
                else:
                    self._update(session, job, "repairing", 45, f"repairing_attempt_{attempt}")
                    if isinstance(last_error, VisualReviewError):
                        repair_hint = last_error.result.repair_hint()
                    else:
                        repair_hint = f"{type(last_error).__name__}: {last_error}"
                    blueprint = self.llm.repair_blueprint(
                        job.prompt,
                        blueprint_data or {},
                        repair_hint,
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

                self._update(session, job, "manim_generation", 20, "materializing_sources")
                video_dir = self.materializer.materialize(blueprint, workspace)
                logger.info("job.sources.materialized job_id=%s video_dir=%s", job.id, video_dir)

                self._update(session, job, "manim_generation", 26, "scene_codegen")
                scene_codes = self._generate_scene_codes(blueprint, video_dir)
                if scene_codes:
                    self.materializer.write_scene_codes(video_dir, blueprint, scene_codes)

                self._update(session, job, "static_validation", 30, "static_validation")
                validate_static_video_source(video_dir)
                logger.info("job.static_validation.done job_id=%s video_dir=%s", job.id, video_dir)

                self._update(session, job, "voice_generation", 40, "voice_generation")
                voice_args, voice_env = voice_command_for_settings(self.settings)
                logger.info(
                    "job.voice.start job_id=%s engine=%s model=%s",
                    job.id,
                    self.settings.voice_engine,
                    self.settings.openai_tts_model if self.settings.voice_engine.strip().lower() == "openai" else "",
                )
                runner.run(voice_args, cwd=video_dir, log_name="voice.log", env=voice_env)
                logger.info("job.voice.done job_id=%s engine=%s", job.id, self.settings.voice_engine)

                self._update(session, job, "render_low_quality", 52, "render_low_quality")
                runner.run(["./render_en.sh"], cwd=video_dir, log_name="render-low.log", env={"QUALITY": "ql"})
                logger.info("job.render_low_quality.done job_id=%s", job.id)

                self._update(session, job, "assemble_low_quality", 62, "assemble_low_quality")
                runner.run(["./assemble_en.sh"], cwd=video_dir, log_name="assemble-low.log")
                logger.info("job.assemble_low_quality.done job_id=%s", job.id)

                requested_target = job.target_duration_seconds or self.settings.default_target_duration_seconds
                minimum_duration = _minimum_final_duration(
                    requested_target,
                    self.settings.default_min_duration_seconds,
                )
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

                visual_review_result: VisualReviewResult | None = None
                if self.settings.visual_review_enabled and not self.settings.fake_llm:
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
                runner.run(["./render_en.sh"], cwd=video_dir, log_name="render-final.log", env={"QUALITY": "qh"})
                logger.info("job.render_final.done job_id=%s", job.id)

                self._update(session, job, "assemble_final", 88, "assemble_final")
                runner.run(["./assemble_en.sh"], cwd=video_dir, log_name="assemble-final.log")
                logger.info("job.assemble_final.done job_id=%s", job.id)

                final_video = video_dir / "final" / f"{blueprint.slug}-en-final.mp4"
                self._update(session, job, "verify_final", 94, "verify_final")
                final_report = verify_mp4(
                    final_video,
                    runner,
                    final_quality=True,
                    report_dir=reports_dir / "final",
                    min_duration_seconds=minimum_duration,
                )
                if visual_review_result is not None:
                    final_report["visual_review"] = json.loads(visual_review_result.model_dump_json())
                report_path = reports_dir / "report.json"
                report_path.write_text(json.dumps(final_report, indent=2) + "\n", encoding="utf-8")
                job.final_video_path = str(final_video)
                job.report_path = str(report_path)
                self._update(session, job, "completed", 100, "completed")
                logger.info("job.completed job_id=%s final_video=%s report=%s", job.id, final_video, report_path)
                return
            except Exception as exc:
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


    def _generate_scene_codes(self, blueprint: VideoBlueprint, video_dir: Path) -> dict[str, str]:
        """Generate LLM Manim code for each scene with a repair loop + deterministic fallback.

        Each candidate is checked for security, syntax, undefined names, and — unless
        disabled — proven to render via a single-scene smoke render. A scene that fails
        every attempt is omitted so the materializer uses its deterministic fallback
        template, guaranteeing the global render still succeeds.

        Returns a dict mapping scene_key → full class code string.
        """
        if not self.settings.scene_coder_enabled:
            logger.info("scene_codegen.skip reason=deterministic_only (VIDEO_API_SCENE_CODER_ENABLED=0)")
            return {}
        if self.settings.fake_llm or not self.settings.openai_api_key:
            logger.info("scene_codegen.skip fake_llm=%s has_key=%s", self.settings.fake_llm, bool(self.settings.openai_api_key))
            return {}

        slug_module = blueprint.slug.replace("-", "_")
        scene_codes: dict[str, str] = {}
        for scene in blueprint.scenes:
            prev_code: str = ""
            prev_error: str = ""
            succeeded = False
            for attempt in range(self.settings.scene_coder_attempts):
                code: str = ""
                try:
                    if attempt == 0:
                        code = self.scene_coder.generate(scene, blueprint)
                    else:
                        code = self.scene_coder.repair(scene, blueprint, prev_code, prev_error)

                    validate_scene_ast_security(code, scene.key)
                    ast.parse(code)

                    if self.settings.scene_coder_smoke_render:
                        module_source = build_single_scene_module(slug_module, code)
                        validate_scene_names(module_source, scene.key)
                        smoke_render_scene(
                            video_dir,
                            scene.key,
                            module_source,
                            self.settings.scene_coder_smoke_timeout_seconds,
                        )

                    scene_codes[scene.key] = code
                    succeeded = True
                    logger.info(
                        "scene_codegen.success scene=%s attempt=%d",
                        scene.key,
                        attempt,
                    )
                    break
                except Exception as exc:
                    prev_error = str(exc)
                    prev_code = code
                    logger.warning(
                        "scene_codegen.attempt_failed scene=%s attempt=%d error=%s",
                        scene.key,
                        attempt,
                        exc,
                    )

            if not succeeded:
                logger.warning(
                    "scene_codegen.fallback scene=%s using deterministic template after %d attempts",
                    scene.key,
                    self.settings.scene_coder_attempts,
                )

        logger.info(
            "scene_codegen.done total=%d llm=%d fallback=%d",
            len(blueprint.scenes),
            len(scene_codes),
            len(blueprint.scenes) - len(scene_codes),
        )
        return scene_codes


def _minimum_final_duration(target_duration_seconds: int, default_min_duration_seconds: int) -> int:
    return timing.minimum_final_duration(target_duration_seconds, default_min_duration_seconds)
