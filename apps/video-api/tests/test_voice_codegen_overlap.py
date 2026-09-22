"""Remotion TSX reuse across repairs, and the voice running during scene coding."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from video_api.config import Settings
from video_api.db import SessionLocal
from video_api.models import VideoJob
from video_api.pipeline.engine import RemotionEngine
from video_api.pipeline.llm import LLMClient
from video_api.pipeline.remotion_blueprint import fake_remotion_blueprint
from video_api.pipeline.substep import TTSSegmentReporter
from video_api.schemas import RemotionBlueprint

from .test_pipeline_flow import _pipeline

_REPO_ROOT = Path(__file__).resolve().parents[3]


# --------------------------------------------------------------------------- #
# Remotion: validated Custom TSX is reused while its coder input is unchanged
# --------------------------------------------------------------------------- #
def _custom_blueprint(custom_indexes: tuple[int, ...]) -> RemotionBlueprint:
    data = fake_remotion_blueprint("x", "cs", 240).model_dump()
    for index in custom_indexes:
        data["scenes"][index]["component"] = "Custom"
        data["scenes"][index]["visual_intent"] = f"draw diagram number {index}"
    return RemotionBlueprint.model_validate(data)


def _remotion_engine() -> tuple[RemotionEngine, list[list[str]], MagicMock]:
    settings = Settings(
        repo_root=_REPO_ROOT,
        fake_llm=False,
        openai_api_key="test-key",
        scene_coder_enabled=True,
        scene_coder_smoke_render=False,
    )
    engine = RemotionEngine(settings, LLMClient(settings))
    waves: list[list[str]] = []

    def code_scenes(custom, blueprint, remotion_dir, public_dir):
        waves.append([scene.key for scene in custom])
        return {
            scene.key: f"export const {scene.key}: React.FC<any> = () => null; // {len(waves)}"
            for scene in custom
        }

    engine.scene_coder._code_scenes_in_waves = code_scenes
    materializer = MagicMock()
    engine.materializer = materializer
    return engine, waves, materializer


def test_remotion_engine_reuses_tsx_for_unchanged_custom_scenes(tmp_path: Path) -> None:
    engine, waves, materializer = _remotion_engine()
    blueprint = _custom_blueprint((1, 2))
    keys = [blueprint.scenes[1].key, blueprint.scenes[2].key]

    engine.generate_scenes(blueprint, tmp_path)
    assert sorted(waves[-1]) == sorted(keys)
    first_codes = materializer.write_scene_codes.call_args.args[2]

    # A repair that rewrites scene 2 only: scene 1 keeps its validated code.
    blueprint.scenes[2].visual_intent = "draw a different diagram"
    engine.generate_scenes(blueprint, tmp_path)
    assert waves[-1] == [keys[1]]
    codes = materializer.write_scene_codes.call_args.args[2]
    assert set(codes) == set(keys)
    assert codes[keys[0]] == first_codes[keys[0]]

    # Nothing changed: no LLM wave at all.
    calls = len(waves)
    engine.generate_scenes(blueprint, tmp_path)
    assert len(waves) == calls

    engine.forget_scene_codes({keys[0]})
    engine.generate_scenes(blueprint, tmp_path)
    assert waves[-1] == [keys[0]]

    engine.forget_scene_codes()
    engine.generate_scenes(blueprint, tmp_path)
    assert sorted(waves[-1]) == sorted(keys)


def test_remotion_scene_code_is_not_reused_after_fallback(tmp_path: Path, monkeypatch) -> None:
    engine, waves, _ = _remotion_engine()
    blueprint = _custom_blueprint((1,))
    key = blueprint.scenes[1].key
    monkeypatch.setattr(
        "video_api.pipeline.remotion_materialize.fallback_custom_to_palette",
        lambda *a, **k: None,
    )

    def failing(custom, *_):
        waves.append([scene.key for scene in custom])
        return {}

    engine.scene_coder._code_scenes_in_waves = failing
    engine.generate_scenes(blueprint, tmp_path)
    engine.generate_scenes(blueprint, tmp_path)
    assert waves == [[key], [key]]


# --------------------------------------------------------------------------- #
# Deferred TTS reporter: counts in the background, writes once activated
# --------------------------------------------------------------------------- #
def test_deferred_tts_reporter_writes_only_after_activate() -> None:
    session = MagicMock()
    job = SimpleNamespace(id="j", substep_unit=None, substep_current=None, substep_total=None)
    reporter = TTSSegmentReporter(session, job, total_segments=4, deferred=True)

    reporter("stdout", "Generating Kokoro segment Scene1EN")
    reporter("stdout", "Generating Kokoro segment Scene2EN")
    session.commit.assert_not_called()

    reporter.activate()
    assert (job.substep_unit, job.substep_current, job.substep_total) == ("segments", 2, 4)
    reporter("stdout", "Generating Kokoro segment Scene3EN")
    assert job.substep_current == 3
    assert session.commit.call_count == 2


# --------------------------------------------------------------------------- #
# Pipeline: voice starts right after materialization
# --------------------------------------------------------------------------- #
class _VoiceRunner:
    """Voice command (["voice"]) runs on its own schedule; other commands record."""

    def __init__(self, voice_delay: float = 0.0, voice_error: Exception | None = None) -> None:
        self.calls: list[str] = []
        self.voice_started = threading.Event()
        self.voice_finished = threading.Event()
        self.voice_delay = voice_delay
        self.voice_error = voice_error

    def run(self, args: list[str], cwd: Path, log_name: str, env: Any = None, on_line: Any = None):
        self.calls.append(log_name)
        if args == ["voice"]:
            self.voice_started.set()
            time.sleep(self.voice_delay)
            self.voice_finished.set()
            if self.voice_error is not None:
                raise self.voice_error
        return CompletedProcess(args, 0, stdout="", stderr="")


def _overlap_pipeline(tmp_path: Path, monkeypatch, job_id: str, overlap: bool):
    import dataclasses

    import video_api.pipeline.production as production

    pipeline, _, job_id, _ = _pipeline(
        tmp_path, monkeypatch, review_passes=True, max_repairs=0, job_id=job_id
    )
    pipeline.settings = dataclasses.replace(pipeline.settings, voice_codegen_overlap=overlap)
    monkeypatch.setattr(production, "voice_command_for_settings", lambda s: (["voice"], None))
    workspace = Path(pipeline.settings.jobs_root) / job_id
    workspace.mkdir(parents=True, exist_ok=True)
    return pipeline, job_id, workspace


def test_voice_runs_during_scene_codegen(tmp_path: Path, monkeypatch) -> None:
    pipeline, job_id, workspace = _overlap_pipeline(tmp_path, monkeypatch, "job-voice-overlap", True)
    runner = _VoiceRunner(voice_delay=0.05)
    seen_during_codegen: list[bool] = []

    def generate_scenes(*_a, **_k):
        seen_during_codegen.append(runner.voice_started.wait(timeout=5))

    pipeline.engine.generate_scenes.side_effect = generate_scenes

    with SessionLocal() as session:
        job = session.get(VideoJob, job_id)
        pipeline._run_with_repairs(session, job, workspace, runner, workspace / "reports")
        assert job.status == "completed"

    assert seen_during_codegen == [True]
    assert runner.calls.index("voice.log") < runner.calls.index("render-final.log")
    report = json.loads((workspace / "reports" / "report.json").read_text(encoding="utf-8"))
    assert report["voice"]["overlap"] == "scene_codegen"
    assert report["voice"]["seconds"] >= report["voice"]["wait_seconds"] >= 0


def test_voice_after_codegen_when_overlap_disabled(tmp_path: Path, monkeypatch) -> None:
    pipeline, job_id, workspace = _overlap_pipeline(tmp_path, monkeypatch, "job-voice-serial", False)
    runner = _VoiceRunner()
    started_during_codegen: list[bool] = []
    pipeline.engine.generate_scenes.side_effect = lambda *a, **k: started_during_codegen.append(
        runner.voice_started.is_set()
    )

    with SessionLocal() as session:
        job = session.get(VideoJob, job_id)
        pipeline._run_with_repairs(session, job, workspace, runner, workspace / "reports")

    assert started_during_codegen == [False]
    report = json.loads((workspace / "reports" / "report.json").read_text(encoding="utf-8"))
    assert report["voice"]["overlap"] == "off"


def test_background_voice_error_fails_at_voice_step(tmp_path: Path, monkeypatch) -> None:
    pipeline, job_id, workspace = _overlap_pipeline(tmp_path, monkeypatch, "job-voice-error", True)
    runner = _VoiceRunner(voice_error=RuntimeError("remote TTS unavailable"))

    with SessionLocal() as session:
        job = session.get(VideoJob, job_id)
        with pytest.raises(RuntimeError, match="remote TTS unavailable"):
            pipeline._run_with_repairs(session, job, workspace, runner, workspace / "reports")
        assert job.current_step == "voice_generation"
    assert "render-final.log" not in runner.calls


def test_codegen_failure_waits_for_background_voice(tmp_path: Path, monkeypatch) -> None:
    pipeline, job_id, workspace = _overlap_pipeline(tmp_path, monkeypatch, "job-voice-wait", True)
    runner = _VoiceRunner(voice_delay=0.2)

    def generate_scenes(*_a, **_k):
        runner.voice_started.wait(timeout=5)
        raise ValueError("static validation failed")

    pipeline.engine.generate_scenes.side_effect = generate_scenes

    with SessionLocal() as session:
        job = session.get(VideoJob, job_id)
        with pytest.raises(ValueError, match="static validation failed"):
            pipeline._run_with_repairs(session, job, workspace, runner, workspace / "reports")
    assert runner.voice_finished.is_set()
