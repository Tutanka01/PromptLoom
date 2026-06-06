from __future__ import annotations

import json
import logging
import shlex
import traceback
from pathlib import Path

from sqlalchemy.orm import Session

from video_api.config import Settings, get_settings
from video_api.db import SessionLocal
from video_api.models import VideoJob
from video_api.pipeline.commands import CommandRunner
from video_api.pipeline.llm import LLMClient
from video_api.pipeline.materialize import Materializer
from video_api.pipeline.validate import validate_static_video_source
from video_api.pipeline.verify import verify_mp4
from video_api.storage import job_root


logger = logging.getLogger(__name__)


class VideoPipeline:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.llm = LLMClient(self.settings)
        self.materializer = Materializer(self.settings)

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

    def run(self, job_id: str) -> None:
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
            except Exception as exc:
                current_step = job.current_step or ""
                if "verify" in current_step:
                    failure_status = "failed_quality"
                elif current_step in {"planning", "materializing_sources", "static_validation"}:
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
                    blueprint = self.llm.generate_blueprint(job.prompt, job.theme, None)
                else:
                    self._update(session, job, "repairing", 45, f"repairing_attempt_{attempt}")
                    blueprint = self.llm.repair_blueprint(
                        job.prompt,
                        blueprint_data or {},
                        f"{type(last_error).__name__}: {last_error}",
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

                self._update(session, job, "static_validation", 30, "static_validation")
                validate_static_video_source(video_dir)
                logger.info("job.static_validation.done job_id=%s video_dir=%s", job.id, video_dir)

                self._update(session, job, "voice_generation", 40, "voice_generation")
                runner.run(shlex.split(self.settings.voice_command), cwd=video_dir, log_name="voice.log")
                logger.info("job.voice.done job_id=%s", job.id)

                self._update(session, job, "render_low_quality", 52, "render_low_quality")
                runner.run(["./render_en.sh"], cwd=video_dir, log_name="render-low.log", env={"QUALITY": "ql"})
                logger.info("job.render_low_quality.done job_id=%s", job.id)

                self._update(session, job, "assemble_low_quality", 62, "assemble_low_quality")
                runner.run(["./assemble_en.sh"], cwd=video_dir, log_name="assemble-low.log")
                logger.info("job.assemble_low_quality.done job_id=%s", job.id)

                final_low = video_dir / "final" / f"{blueprint.slug}-en-final.mp4"
                self._update(session, job, "verify_low_quality", 68, "verify_low_quality")
                verify_mp4(final_low, runner, final_quality=False, report_dir=reports_dir / "low")
                logger.info("job.verify_low_quality.done job_id=%s video=%s", job.id, final_low)

                self._update(session, job, "render_final", 78, "render_final")
                runner.run(["./render_en.sh"], cwd=video_dir, log_name="render-final.log", env={"QUALITY": "qh"})
                logger.info("job.render_final.done job_id=%s", job.id)

                self._update(session, job, "assemble_final", 88, "assemble_final")
                runner.run(["./assemble_en.sh"], cwd=video_dir, log_name="assemble-final.log")
                logger.info("job.assemble_final.done job_id=%s", job.id)

                final_video = video_dir / "final" / f"{blueprint.slug}-en-final.mp4"
                self._update(session, job, "verify_final", 94, "verify_final")
                final_report = verify_mp4(final_video, runner, final_quality=True, report_dir=reports_dir / "final")
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
