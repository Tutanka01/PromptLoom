"""Render-engine strategy: Manim (default) vs Remotion, selected by settings.

The shared orchestrator (pipeline/production.py) drives the job lifecycle —
repair loop, voice, render, assemble, verify, visual review — and delegates the
four engine-specific steps to an ``Engine``:

    plan -> materialize -> generate_scenes -> validate_static

Everything downstream of ``materialize`` is identical between engines because
both write the same ``video_dir`` contract (segments_en.json / generate_voice_en.py
/ render_en.sh / assemble_en.sh).
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any, Protocol

from video_api.config import Settings
from video_api.pipeline.llm import LLMClient

logger = logging.getLogger(__name__)


class Engine(Protocol):
    name: str
    # The frame rate the engine actually writes, so verify can assert it. Manim's
    # quality presets fix this (qh == 60); Remotion honors settings.render_fps.
    output_fps: float

    def generate_blueprint(self, prompt: str, theme: str | None, target: int | None) -> Any: ...

    def repair_blueprint(self, prompt: str, previous: dict, hint: str) -> Any: ...

    def materialize(self, blueprint: Any, workspace: Path) -> Path: ...

    def generate_scenes(self, blueprint: Any, video_dir: Path) -> None: ...

    def validate_static(self, video_dir: Path) -> None: ...


class ManimEngine:
    name = "manim"
    # Manim's -qh quality preset renders at 1080p60; render_fps does not apply here.
    output_fps = 60.0

    def __init__(self, settings: Settings, llm: LLMClient):
        from video_api.pipeline.materialize import Materializer
        from video_api.pipeline.scene_coder import SceneCoder

        self.settings = settings
        self.llm = llm
        self.materializer = Materializer(settings)
        self.scene_coder = SceneCoder(settings)

    def generate_blueprint(self, prompt: str, theme: str | None, target: int | None) -> Any:
        return self.llm.generate_blueprint(prompt, theme, target)

    def repair_blueprint(self, prompt: str, previous: dict, hint: str) -> Any:
        return self.llm.repair_blueprint(prompt, previous, hint)

    def materialize(self, blueprint: Any, workspace: Path) -> Path:
        return self.materializer.materialize(blueprint, workspace)

    def generate_scenes(self, blueprint: Any, video_dir: Path) -> None:
        scene_codes = self._generate_scene_codes(blueprint, video_dir)
        if scene_codes:
            self.materializer.write_scene_codes(video_dir, blueprint, scene_codes)

    def validate_static(self, video_dir: Path) -> None:
        from video_api.pipeline.validate import validate_static_video_source

        validate_static_video_source(video_dir)

    def _generate_scene_codes(self, blueprint: Any, video_dir: Path) -> dict[str, str]:
        """LLM Manim code per scene with repair loop + deterministic fallback.

        Each candidate is checked for security, syntax, undefined names and —
        unless disabled — proven to render via a single-scene smoke render. A
        scene that fails every attempt is omitted so the materializer uses its
        deterministic fallback template, guaranteeing the global render succeeds.
        """
        from video_api.pipeline.materialize import build_single_scene_module
        from video_api.pipeline.validate import (
            smoke_render_scene,
            validate_scene_ast_security,
            validate_scene_names,
        )

        if not self.settings.scene_coder_enabled:
            logger.info("scene_codegen.skip reason=deterministic_only (VIDEO_API_SCENE_CODER_ENABLED=0)")
            return {}
        if self.settings.fake_llm or not self.settings.openai_api_key:
            logger.info("scene_codegen.skip fake_llm=%s has_key=%s", self.settings.fake_llm, bool(self.settings.openai_api_key))
            return {}

        slug_module = blueprint.slug.replace("-", "_")
        scene_codes: dict[str, str] = {}
        for scene in blueprint.scenes:
            prev_code = ""
            prev_error = ""
            succeeded = False
            for attempt in range(self.settings.scene_coder_attempts):
                code = ""
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
                    logger.info("scene_codegen.success scene=%s attempt=%d", scene.key, attempt)
                    break
                except Exception as exc:
                    prev_error = str(exc)
                    prev_code = code
                    logger.warning("scene_codegen.attempt_failed scene=%s attempt=%d error=%s", scene.key, attempt, exc)
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


class RemotionEngine:
    name = "remotion"

    def __init__(self, settings: Settings, llm: LLMClient):
        from video_api.pipeline.remotion_materialize import RemotionMaterializer
        from video_api.pipeline.remotion_scene_coder import RemotionSceneCoder

        self.settings = settings
        self.llm = llm
        self.materializer = RemotionMaterializer(settings)
        self.scene_coder = RemotionSceneCoder(settings)
        # Remotion renders at the configured frame rate (default 30).
        self.output_fps = float(settings.render_fps)

    def generate_blueprint(self, prompt: str, theme: str | None, target: int | None) -> Any:
        return self.llm.generate_remotion_blueprint(prompt, theme, target)

    def repair_blueprint(self, prompt: str, previous: dict, hint: str) -> Any:
        return self.llm.repair_remotion_blueprint(prompt, previous, hint)

    def materialize(self, blueprint: Any, workspace: Path) -> Path:
        return self.materializer.materialize(blueprint, workspace)

    def generate_scenes(self, blueprint: Any, video_dir: Path) -> None:
        self.scene_coder.generate_custom_scenes(blueprint, video_dir, self.materializer)

    def validate_static(self, video_dir: Path) -> None:
        from video_api.pipeline.remotion_materialize import validate_remotion_video_source

        validate_remotion_video_source(video_dir)


def make_engine(settings: Settings, llm: LLMClient) -> Engine:
    engine = (settings.render_engine or "manim").strip().lower()
    if engine == "remotion":
        logger.info("engine.select engine=remotion")
        return RemotionEngine(settings, llm)
    if engine not in {"manim", ""}:
        logger.warning("engine.unknown engine=%s falling back to manim", engine)
    logger.info("engine.select engine=manim")
    return ManimEngine(settings, llm)
