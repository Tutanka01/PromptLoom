from __future__ import annotations

import json
import logging
import threading
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
from video_api.event_bus import publish_job_snapshot
from video_api.models import VideoJob
from video_api.pipeline.commands import CommandRunner
from video_api.pipeline.engine import make_engine
from video_api.pipeline.editorial import MotionQualityError, write_editorial_artifacts
from video_api.pipeline.llm import LLMClient
from video_api.pipeline.verify import verify_mp4
from video_api.pipeline.visual_review import VisualReviewer
from video_api.pipeline.substep import (
    ManimSceneReporter,
    SubstepReporter,
    TTSSegmentReporter,
    parse_remotion_frame,
    set_substep,
)
from video_api.pipeline.voice import voice_command_for_settings
from video_api.schemas import VisualReviewResult
from video_api.schemas import ProductionOptions
from video_api.storage import job_root
from video_api.voices import VoiceSelectionError, apply_job_voice


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
        self.production_options = ProductionOptions()
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

    def _apply_production_config(self, raw: str | None) -> None:
        """Resolve the persisted per-job configuration into one Settings
        snapshot before selecting the render engine."""
        if raw:
            try:
                options = ProductionOptions.model_validate_json(raw)
            except Exception as exc:
                raise RuntimeError(f"invalid persisted production_config: {exc}") from exc
        else:
            options = ProductionOptions()
        self.production_options = options
        engine = options.render_engine or self.settings.render_engine
        transition_profile = {
            "technical": "minimal",
            "editorial": "editorial",
            "cinematic": "cinematic",
        }[options.mode]
        render_fps = 60 if options.mode == "cinematic" and engine == "remotion" else self.settings.render_fps
        self.settings = dataclasses.replace(
            self.settings,
            render_engine=engine,
            production_mode=options.mode,
            caption_mode=options.captions or "off",
            transition_profile=transition_profile,
            delivery_promise=options.delivery_promise or "technical_explainer",
            render_fps=render_fps,
        )
        self.llm = LLMClient(self.settings)
        self.engine = make_engine(self.settings, self.llm)
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
        # Every status transition clears any lingering sub-step counter: the
        # UI would otherwise still show 'frames 4429/4429' during
        # assemble_final. Individual steps that want a sub-counter re-populate
        # these columns via SubstepReporter / set_substep while they run.
        job.substep_unit = None
        job.substep_current = None
        job.substep_total = None
        job.substep_eta_seconds = None
        session.add(job)
        session.commit()
        # Fan-out to SSE subscribers (Studio, curl consumers, external monitors).
        # Silent on failure — the DB write is authoritative; the event stream
        # is a strict advisory that clients can also reconstruct from polling.
        publish_job_snapshot(job)
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

    def _set_attempt_state(
        self,
        session: Session,
        job: VideoJob,
        attempt_number: int,
        max_attempts: int,
        last_repair_reason: str | None = None,
    ) -> None:
        """Persist repair-loop metadata to the DB row so the API (and Studio)
        can display it. Called at the top of each iteration in
        ``_run_with_repairs`` and again once the repair reason is known.

        ``attempt_number`` is 0 for the first run and increments on every
        retry. ``max_attempts`` is the ceiling (``settings.max_repair_attempts
        + 1``). ``last_repair_reason`` is only set when we know it — passing
        None here preserves the previous value rather than clearing it.
        """
        job.attempt_number = attempt_number
        job.max_attempts = max_attempts
        if last_repair_reason is not None:
            job.last_repair_reason = last_repair_reason
        session.add(job)
        session.commit()

    def _load_master_blueprint(self, session: Session, job: VideoJob) -> dict | None:
        """For a secondary batch job, load the primary sibling's validated
        blueprint.json (the master to translate). Returns None for ordinary
        single-language jobs and for the primary itself.

        Raises if a secondary cannot find a usable master: secondaries are only
        ever enqueued after the primary completes, so a missing master is a real
        error, not a reason to silently regenerate (which would break the
        identical-content guarantee)."""
        if not job.batch_id or job.is_primary:
            return None
        primary = session.execute(
            select(VideoJob).where(
                VideoJob.batch_id == job.batch_id,
                VideoJob.is_primary.is_(True),
            )
        ).scalar_one_or_none()
        if primary is None:
            raise RuntimeError(f"batch {job.batch_id}: no primary job found for secondary {job.id}")
        master_path = job_root(self.settings.jobs_root, primary.id) / "blueprint.json"
        if not master_path.exists():
            raise RuntimeError(
                f"batch {job.batch_id}: master blueprint missing at {master_path} "
                f"(primary {primary.id} status={primary.status})"
            )
        return json.loads(master_path.read_text(encoding="utf-8"))

    def _load_master_research(self, session: Session, job: VideoJob) -> dict | None:
        if not job.batch_id or job.is_primary:
            return None
        primary = session.execute(
            select(VideoJob).where(
                VideoJob.batch_id == job.batch_id,
                VideoJob.is_primary.is_(True),
            )
        ).scalar_one_or_none()
        if primary is None:
            return None
        path = job_root(self.settings.jobs_root, primary.id) / "research.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def _prepare_research(self, session: Session, job: VideoJob, workspace: Path) -> Any | None:
        from video_api.pipeline.research import ResearchDossier, Researcher

        options = self.production_options.research
        if not options.enabled:
            return None
        master = self._load_master_research(session, job)
        if master is not None:
            dossier = ResearchDossier.model_validate(master)
        else:
            self._update(session, job, "planning", 3, "researching")
            dossier = Researcher(self.settings).research(
                job.prompt,
                max_sources=options.max_sources,
                required=options.required,
            )
        (workspace / "research.json").write_text(dossier.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return dossier

    def _notify_terminal(self, session: Session, job: VideoJob) -> None:
        """Best-effort terminal webhook; never raises into the pipeline."""
        try:
            from video_api.webhooks import notify_job_terminal

            session.refresh(job)
            notify_job_terminal(job, self.settings)
        except Exception:
            logger.exception("job.webhook.error job_id=%s", job.id)

    def _assemble_env(self) -> dict[str, str] | None:
        return {
            "VOICE_MASTERING_ENABLED": "1" if self.settings.voice_mastering_enabled else "0",
            "LOUDNORM_ENABLED": "1" if self.settings.audio_loudnorm_enabled else "0",
            "LOUDNESS_TARGET": f"{self.settings.audio_loudness_target_lufs:g}",
            "LOUDNESS_TP": f"{self.settings.audio_true_peak_db:g}",
        }

    def run(self, job_id: str) -> str:
        with SessionLocal() as session:
            job = session.get(VideoJob, job_id)
            if job is None:
                raise RuntimeError(f"job not found: {job_id}")
            self._apply_profile(getattr(job, "quality_profile", None))
            self._apply_production_config(getattr(job, "production_config", None))
            self.settings = dataclasses.replace(self.settings, voice_language=job.language or "en")
            try:
                # Freeze the requested (or language-appropriate default) voice
                # into the snapshot BEFORE the engine is rebuilt: the engine and
                # the audio-cache signature both read these settings. A voice
                # that disappeared since request time fails the job clearly —
                # no silent fallback to another timbre.
                self.settings = apply_job_voice(self.settings, self.production_options.voice)
            except VoiceSelectionError as exc:
                logger.error("job.voice.unavailable job_id=%s error=%s", job_id, exc)
                self._update(session, job, "failed_generation", job.progress or 0, "voice_selection", error=str(exc))
                self._notify_terminal(session, job)
                return job.status
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
                research = self._prepare_research(session, job, workspace)
                self._run_with_repairs(session, job, workspace, runner, reports_dir, research)
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
                elif current_step in {
                    "researching", "planning", "asset_acquisition", "motion_preflight",
                    "materializing_sources", "static_validation",
                } or current_step.startswith("repairing"):
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
        research: Any | None = None,
    ) -> None:
        last_error: Exception | None = None
        blueprint_data: dict | None = None
        max_attempts = self.settings.max_repair_attempts + 1
        for attempt in range(max_attempts):
            try:
                logger.info(
                    "job.attempt.start job_id=%s attempt=%d max_attempts=%d",
                    job.id,
                    attempt,
                    self.settings.max_repair_attempts,
                )
                self._set_attempt_state(session, job, attempt, max_attempts)
                if attempt == 0:
                    master = self._load_master_blueprint(session, job)
                    if master is not None:
                        # Secondary job of a multi-language batch: translate the
                        # primary's validated master instead of regenerating, so
                        # every language shares identical content and structure.
                        self._update(session, job, "planning", 5, "translating")
                        logger.info(
                            "job.translate.start job_id=%s batch_id=%s language=%s",
                            job.id,
                            job.batch_id,
                            job.language,
                        )
                        blueprint = self.engine.translate_blueprint(master, job.language)
                    else:
                        self._update(session, job, "planning", 5, "planning")
                        blueprint = self.engine.generate_blueprint(
                            job.prompt,
                            job.theme,
                            job.target_duration_seconds,
                            job.language,
                            self.production_options.model_dump(),
                            research.prompt_context() if research is not None else None,
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
                    elif isinstance(last_error, MotionQualityError):
                        repair_hint = last_error.repair_hint()
                    else:
                        repair_hint = f"{type(last_error).__name__}: {last_error}"
                    # Surface the reason to the API row so the Studio can show
                    # "Réparation 1/2 — MotionQualityError: ..." instead of a
                    # silent second planning pass.
                    self._set_attempt_state(
                        session, job, attempt, max_attempts, last_repair_reason=repair_hint
                    )
                    if blueprint is None:
                        blueprint = self.engine.repair_blueprint(
                            job.prompt,
                            blueprint_data or {},
                            repair_hint,
                            job.language,
                            self.production_options.model_dump(),
                            research.prompt_context() if research is not None else None,
                            target=job.target_duration_seconds,
                        )
                # Never allow an LLM to invent provenance identifiers. Fake
                # mode attaches its deterministic fixture so advanced smoke
                # tests exercise the complete sourced path.
                valid_source_ids = {source.id for source in getattr(research, "sources", [])}
                for scene in blueprint.scenes:
                    current = list(getattr(scene, "source_ids", []) or [])
                    filtered = [source_id for source_id in current if source_id in valid_source_ids]
                    if self.settings.fake_llm and valid_source_ids and not filtered:
                        filtered = [sorted(valid_source_ids)[0]]
                    if hasattr(scene, "source_ids"):
                        scene.source_ids = filtered

                asset_manifest = None
                if self.engine.name == "remotion":
                    from video_api.pipeline.assets import AssetResolver

                    self._update(session, job, "generating_sources", 16, "asset_acquisition")
                    asset_manifest = AssetResolver(self.settings).resolve(
                        blueprint,
                        workspace,
                        allow_stock=bool(self.production_options.visuals.allow_stock),
                        max_assets=self.production_options.visuals.max_assets,
                    )

                self._update(session, job, "planning", 18, "motion_preflight")
                blueprint_data = blueprint.model_dump()
                motion_plan = write_editorial_artifacts(
                    workspace, blueprint, self.production_options, research, asset_manifest
                )
                (workspace / f"motion_plan_report_attempt_{attempt}.json").write_text(
                    json.dumps(motion_plan, indent=2) + "\n",
                    encoding="utf-8",
                )
                logger.info(
                    "job.motion_preflight.done job_id=%s attempt=%d score=%.1f minimum=%.1f "
                    "score_passed=%s passed=%s blockers=%d warnings=%d components=%s",
                    job.id,
                    attempt,
                    motion_plan["score"],
                    motion_plan["minimum_score"],
                    motion_plan["score_passed"],
                    motion_plan["passed"],
                    len(motion_plan["blocking_issues"]),
                    len(motion_plan["warnings"]),
                    json.dumps(motion_plan["component_mix"], sort_keys=True),
                )
                if self.production_options.mode != "technical" and not motion_plan["passed"]:
                    raise MotionQualityError(motion_plan)
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
                # Bump the sub-step counter after each scene the engine finishes
                # coding — the Studio then shows "3/8 scènes générées" while
                # the LLM works through the blueprint. Thread-safe via a lock
                # because the manim coder parallelises scenes.
                _scenes_total = len(blueprint.scenes)
                _scene_count = [0]
                _scene_lock = threading.Lock()

                def _on_scene_done(_key: str) -> None:
                    with _scene_lock:
                        _scene_count[0] += 1
                        current = _scene_count[0]
                    set_substep(session, job, "scenes", current, _scenes_total)
                    publish_job_snapshot(job)

                self.engine.generate_scenes(blueprint, video_dir, on_scene_done=_on_scene_done)

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
                    if self.settings.voice_engine.strip().lower()
                    in {"moss", "moss-tts", "moss_tts", "moss-remote", "moss_remote", "remote-moss"}
                    else "",
                )
                voice_on_line = None
                if self.settings.voice_engine.strip().lower() == "openai":
                    # The openai voice command prints one "Generating ..." line
                    # per segment, so we can count them against the blueprint's
                    # scene count. The other engines (chatterbox, kokoro,
                    # moss[-remote]) don't emit a comparable line yet — a
                    # follow-up can add per-engine parsers if desired.
                    voice_on_line = TTSSegmentReporter(
                        session, job, total_segments=len(blueprint.scenes)
                    )
                runner.run(
                    voice_args,
                    cwd=video_dir,
                    log_name="voice.log",
                    env=voice_env,
                    on_line=voice_on_line,
                )
                logger.info("job.voice.done job_id=%s engine=%s", job.id, self.settings.voice_engine)

                cued_scenes = 0
                subtitle_files: dict[str, str] = {}
                subtitle_cues = 0
                # "skipped" when the engine has no alignment stage; "ok"/"failed"
                # once the stage runs. Alignment stays non-fatal, but the outcome
                # is surfaced in final_report["alignment"] and quality_warnings so
                # a silently degraded (even-grid, caption-less) job is visible.
                align_enabled = self.engine.name == "remotion" and self.settings.align_enabled
                alignment_status = "skipped"
                alignment_error: str | None = None
                if align_enabled:
                    self._update(session, job, "audio_alignment", 44, "audio_alignment")
                    try:
                        from video_api.pipeline.align import align_segments
                        from video_api.pipeline.beats import resolve_cues
                        from video_api.pipeline.captions import write_subtitles

                        align_segments(video_dir, device=self.settings.align_device)
                        cued = resolve_cues(video_dir, blueprint)
                        cued_scenes = len(cued)
                        # Subtitles are opt-in per request: `captions: "off"` ships
                        # a clean video with no burned-in track AND no .srt/.vtt.
                        # Alignment/beats above still run — they drive the visual
                        # cue timing regardless of subtitles.
                        if self.settings.caption_mode != "off":
                            subtitle_cues = write_subtitles(
                                video_dir, slug=blueprint.slug, language=job.language
                            )
                            subtitle_files = _subtitle_artifacts(
                                workspace, video_dir, blueprint.slug, job.language
                            )
                        alignment_status = "ok"
                        logger.info(
                            "job.align.done job_id=%s scenes_with_cues=%d caption_mode=%s subtitle_cues=%d",
                            job.id,
                            len(cued),
                            self.settings.caption_mode,
                            subtitle_cues,
                        )
                    except Exception as align_exc:
                        # Non-fatal: scenes keep their default item timings and the
                        # job ships without burned-in captions / sidecar subtitles.
                        alignment_status = "failed"
                        alignment_error = str(align_exc)
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

                # Render policy: the visual review now inspects the exact file
                # that ships, so there is no separate proxy render. A passing job
                # renders exactly once (previously the review cost an extra
                # half-resolution render); a failing review costs a full
                # re-render by design — the repair loop rewrites the flagged
                # scenes and the next attempt re-renders them at full quality.
                review_enabled = self.settings.visual_review_enabled and not self.settings.fake_llm
                visual_review_result: VisualReviewResult | None = None

                self._update(session, job, "render_final", 55, "render_final")
                final_render_quality = render_quality_for_profile(self.quality_profile)
                render_on_line = None
                if self.engine.name == "remotion":
                    # Remotion's renderMedia prints one "Rendered X/Y" line per
                    # frame; the counter is exactly what the Studio wants.
                    render_on_line = SubstepReporter(
                        session, job, unit="frames", parse=parse_remotion_frame
                    )
                elif self.engine.name == "manim":
                    # Manim doesn't declare an overall frame total (its per-
                    # animation tqdm resets per scene), but it prints
                    # "Rendered SceneName" once per scene — good enough for
                    # "Rendu 2/5 scènes" in the Studio.
                    render_on_line = ManimSceneReporter(
                        session, job, total_scenes=len(blueprint.scenes)
                    )
                runner.run(
                    ["./render_en.sh"],
                    cwd=video_dir,
                    log_name="render-final.log",
                    env={"QUALITY": final_render_quality},
                    on_line=render_on_line,
                )
                logger.info(
                    "job.render_final.done job_id=%s quality=%s", job.id, final_render_quality
                )

                self._update(session, job, "assemble_final", 72, "assemble_final")
                runner.run(
                    ["./assemble_en.sh"],
                    cwd=video_dir,
                    log_name="assemble-final.log",
                    env=self._assemble_env(),
                )
                logger.info("job.assemble_final.done job_id=%s", job.id)

                final_video = video_dir / "final" / f"{blueprint.slug}-en-final.mp4"

                # Review the final assembled MP4 before verify_final so a rejected
                # video is repaired (scene rewrite + re-render on the next
                # attempt) instead of reporting verify stats on a video that is
                # about to be thrown away.
                if review_enabled:
                    self._update(session, job, "visual_review", 80, "visual_review")
                    vr = self.visual_reviewer.review(
                        blueprint,
                        final_video,
                        runner,
                        reports_dir / "review",
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

                self._update(session, job, "verify_final", 92, "verify_final")
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
                    audio_qc_fatal=self.settings.audio_qc_fatal,
                )
                if visual_review_result is not None:
                    final_report["visual_review"] = json.loads(visual_review_result.model_dump_json())
                final_report["quality"] = _quality_summary(blueprint, video_dir, cued_scenes)
                final_report["quality_profile"] = self.quality_profile
                final_report["production"] = self.production_options.model_dump()
                final_report["research"] = {
                    "enabled": research is not None,
                    "provider": getattr(research, "provider", None),
                    "source_count": len(getattr(research, "sources", []) or []),
                }
                final_report["motion_plan"] = motion_plan
                final_report["alignment"] = {
                    "enabled": align_enabled,
                    "status": alignment_status,
                    "error": alignment_error,
                    "scenes_with_cues": cued_scenes,
                    "total_scenes": len(blueprint.scenes),
                    "subtitle_cues": subtitle_cues,
                }
                if alignment_status == "failed":
                    final_report["quality_warnings"].append(
                        f"audio alignment failed ({alignment_error}): scenes shipped with "
                        "default even-grid timings and no subtitles"
                    )
                from video_api.pipeline.editorial import evaluate_rendered_delivery

                final_report["delivery"] = evaluate_rendered_delivery(motion_plan, final_report)
                if self.production_options.mode != "technical" and not final_report["delivery"]["passed"]:
                    raise RuntimeError(
                        "rendered video did not fulfil its delivery promise: "
                        + json.dumps(final_report["delivery"], sort_keys=True)
                    )
                final_report["subtitles"] = subtitle_files
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


def _subtitle_artifacts(
    workspace: Path, video_dir: Path, slug: str, language: str
) -> dict[str, str]:
    """Workspace-relative paths to the sidecar subtitles, for the report.

    These resolve under the generic artifacts endpoint
    (``/v1/videos/{id}/artifacts/<path>``); only files actually written are
    listed so a job without alignment simply reports no subtitles.
    """
    found: dict[str, str] = {}
    for ext in ("srt", "vtt"):
        path = video_dir / "final" / f"{slug}-{language}.{ext}"
        if path.exists():
            try:
                found[ext] = str(path.relative_to(workspace))
            except ValueError:
                found[ext] = str(path)
    return found


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
