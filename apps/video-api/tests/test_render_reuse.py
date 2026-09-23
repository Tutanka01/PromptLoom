from __future__ import annotations

import dataclasses
from pathlib import Path
from types import SimpleNamespace

from video_api import llm_usage
from video_api.config import Settings
from video_api.pipeline.engine import ManimEngine
from video_api.pipeline.llm import LLMClient, fake_blueprint
from video_api.pipeline.production import VideoPipeline, VisualReviewError, _flagged_scene_keys

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _engine() -> tuple[ManimEngine, list[str]]:
    settings = Settings(
        repo_root=_REPO_ROOT,
        fake_llm=False,
        openai_api_key="test-key",
        scene_coder_enabled=True,
        scene_coder_smoke_render=False,
    )
    engine = ManimEngine(settings, LLMClient(settings))
    calls: list[str] = []

    def generate(scene, blueprint):
        calls.append(scene.key)
        return f"class {scene.key}(EnglishGeneratedScene):\n    def construct(self):\n        pass\n"

    engine.scene_coder.generate = generate
    return engine, calls


def test_manim_engine_reuses_code_for_unchanged_scenes(tmp_path: Path) -> None:
    engine, calls = _engine()
    blueprint = fake_blueprint("Explain derivatives", "math")
    keys = [scene.key for scene in blueprint.scenes]

    first = engine._generate_scene_codes(blueprint, tmp_path)
    assert sorted(calls) == sorted(keys)

    calls.clear()
    blueprint.scenes[1].text = blueprint.scenes[1].text + " One more sentence here."
    second = engine._generate_scene_codes(blueprint, tmp_path)
    assert calls == [keys[1]]
    assert second[keys[0]] == first[keys[0]]

    calls.clear()
    engine.forget_scene_codes({keys[0]})
    engine._generate_scene_codes(blueprint, tmp_path)
    assert calls == [keys[0]]

    calls.clear()
    engine.forget_scene_codes()
    engine._generate_scene_codes(blueprint, tmp_path)
    assert sorted(calls) == sorted(keys)


def test_manim_engine_fps_follows_its_own_setting() -> None:
    for fps in (30, 60):
        settings = Settings(repo_root=_REPO_ROOT, manim_render_fps=fps)
        assert ManimEngine(settings, LLMClient(settings)).output_fps == float(fps)


def _review(issues=(), scores=()):
    return SimpleNamespace(
        issues=[SimpleNamespace(severity=s, scene_key=k) for s, k in issues],
        scene_scores=[SimpleNamespace(scene_key=k, score=v) for k, v in scores],
    )


def test_flagged_scene_keys() -> None:
    review = _review(
        issues=[("blocker", "A"), ("minor", "B"), ("major", "unknown")],
        scores=[("C", 40), ("D", 90)],
    )
    assert _flagged_scene_keys(review) == {"A", "C"}


def test_repair_forgets_only_suspect_scene_codes() -> None:
    pipeline = VideoPipeline(Settings(repo_root=_REPO_ROOT, fake_llm=True))
    forgotten: list = []
    pipeline.engine = SimpleNamespace(forget_scene_codes=forgotten.append)

    error = VisualReviewError.__new__(VisualReviewError)
    error.result = _review(issues=[("blocker", "Scene2EN")])
    pipeline._forget_suspect_scene_codes(error, "visual_review")
    error.result = _review()
    pipeline._forget_suspect_scene_codes(error, "visual_review")
    pipeline._forget_suspect_scene_codes(RuntimeError("boom"), "static_validation")
    assert forgotten == [{"Scene2EN"}, None, None]


def test_repair_keeps_scene_codes_when_the_failure_is_not_the_code() -> None:
    """A TTS / alignment / assembly failure says nothing about the scene code, and
    forgetting a scene also invalidates its render cache entry."""
    pipeline = VideoPipeline(Settings(repo_root=_REPO_ROOT, fake_llm=True))
    forgotten: list = []
    pipeline.engine = SimpleNamespace(forget_scene_codes=forgotten.append)

    for step in ("voice_generation", "audio_alignment", "assemble_final"):
        pipeline._forget_suspect_scene_codes(RuntimeError("transient"), step)
    assert forgotten == []


def test_repair_forgets_only_the_scene_manim_named() -> None:
    pipeline = VideoPipeline(Settings(repo_root=_REPO_ROOT, fake_llm=True))
    forgotten: list = []
    pipeline.engine = SimpleNamespace(forget_scene_codes=forgotten.append)

    named = RuntimeError(
        "./render_en.sh failed\nmanim failed for Scene3EN (rc=1), full log: logs/Scene3EN.log"
    )
    pipeline._forget_suspect_scene_codes(named, "render_final")
    # No identifiable scene in the tail -> stay conservative and drop everything.
    pipeline._forget_suspect_scene_codes(RuntimeError("ffmpeg concat failed"), "render_final")
    assert forgotten == [{"Scene3EN"}, None]


def test_manim_failed_scene_keys() -> None:
    from video_api.pipeline.production import _manim_failed_scene_keys

    assert _manim_failed_scene_keys(
        "manim failed for SceneA (rc=1), full log: x\n"
        "manim produced 0 videos for SceneB under media"
    ) == {"SceneA", "SceneB"}
    # The marker render_scenes.py repeats last, so a long Manim traceback cannot
    # push the scene name out of the worker's log tail.
    assert _manim_failed_scene_keys("render.failed scene=SceneC") == {"SceneC"}
    assert _manim_failed_scene_keys("Command './render_en.sh' failed") == set()


def test_llm_usage_accumulates_per_stage() -> None:
    llm_usage.reset()
    response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20))
    llm_usage.record("scene_coder", "m1", response)
    llm_usage.record("scene_coder", "m1", response)
    llm_usage.record("visual_review", "m2", SimpleNamespace(usage=None))
    snap = llm_usage.snapshot()
    assert snap["calls"] == 3
    assert snap["prompt_tokens"] == 200 and snap["completion_tokens"] == 40
    assert snap["by_stage"]["scene_coder"]["models"] == ["m1"]
    assert snap["by_stage"]["visual_review"]["calls"] == 1
    llm_usage.reset()
    assert llm_usage.snapshot()["calls"] == 0


def test_tail_padding_and_overlap_summary() -> None:
    from video_api.pipeline.production import _overlap_summary, _tail_padding

    assert _tail_padding(["python", "generate_voice_en.py", "--tail-padding", "0.450"]) == 0.45
    assert _tail_padding(["python", "generate_voice_en.py"]) is None
    summary = _overlap_summary(
        {"rendered_seconds": {"A": 3.0, "B": 4.0}, "failed": {}},
        {"cached": ["A", "C"]},
    )
    assert summary["reused"] == ["A"] and summary["wasted"] == ["B"]


def test_speculative_render_only_for_manim_with_overlap(tmp_path: Path) -> None:
    blueprint = fake_blueprint("Explain derivatives", "math")
    args = ["python", "generate_voice_en.py", "--tail-padding", "0.45"]
    off = VideoPipeline(Settings(repo_root=_REPO_ROOT, fake_llm=True, voice_render_overlap=False))
    assert off._start_speculative_render(blueprint, tmp_path, args, "qh", "30") is None
    # Off by default, so the overlap has to be opted into explicitly.
    default_off = VideoPipeline(
        Settings(repo_root=_REPO_ROOT, fake_llm=True, render_engine="manim")
    )
    assert default_off._start_speculative_render(blueprint, tmp_path, args, "qh", "30") is None

    remotion = VideoPipeline(
        Settings(
            repo_root=_REPO_ROOT, fake_llm=True, render_engine="remotion", voice_render_overlap=True
        )
    )
    assert remotion._start_speculative_render(blueprint, tmp_path, args, "qh", "30") is None
    manim = VideoPipeline(
        Settings(
            repo_root=_REPO_ROOT, fake_llm=True, render_engine="manim", voice_render_overlap=True
        )
    )
    assert manim._start_speculative_render(blueprint, tmp_path, ["python"], "qh", "30") is None
    spec = manim._start_speculative_render(blueprint, tmp_path, args, "qh", "30")
    assert spec is not None
    spec.stop()


def test_speculative_render_start_failure_is_never_fatal(tmp_path: Path) -> None:
    """Pure optimisation: a bad setting must not raise between the background
    voice thread's start and its join, or that daemon thread outlives the job."""
    blueprint = fake_blueprint("Explain derivatives", "math")
    args = ["python", "generate_voice_en.py", "--tail-padding", "0.45"]
    pipeline = VideoPipeline(
        Settings(
            repo_root=_REPO_ROOT, fake_llm=True, render_engine="manim", voice_render_overlap=True
        )
    )
    pipeline.settings = dataclasses.replace(pipeline.settings, manim_render_jobs="4cpu")
    assert pipeline._start_speculative_render(blueprint, tmp_path, args, "qh", "30") is not None

    def boom(*_args, **_kwargs):
        raise RuntimeError("no manim binary")

    monkeyed = VideoPipeline(
        Settings(
            repo_root=_REPO_ROOT, fake_llm=True, render_engine="manim", voice_render_overlap=True
        )
    )
    import video_api.pipeline.manim_render as mr

    original = mr.SpeculativeRenderer
    mr.SpeculativeRenderer = boom
    try:
        assert monkeyed._start_speculative_render(blueprint, tmp_path, args, "qh", "30") is None
    finally:
        mr.SpeculativeRenderer = original


def test_llm_usage_stage_follows_the_caller_not_the_shared_helper() -> None:
    """_complete is shared by blueprint, translation, scene writing and repair;
    each call has to bill its own stage or the measurement is meaningless."""
    llm_usage.reset()
    settings = Settings(repo_root=_REPO_ROOT, openai_model="m1")
    client_calls: list[str] = []

    class _Completions:
        def create(self, **kwargs):
            client_calls.append(kwargs["model"])
            return SimpleNamespace(
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='{"ok": true}'), finish_reason="stop"
                    )
                ],
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))
    llm = LLMClient(settings)
    for stage in ("blueprint", "translate", "blueprint_repair", "translate"):
        llm._complete(client, [{"role": "user", "content": "x"}],
                      temperature=0.2, json_mode=False, stage=stage)

    by_stage = llm_usage.snapshot()["by_stage"]
    assert set(by_stage) == {"blueprint", "translate", "blueprint_repair"}
    assert by_stage["translate"]["calls"] == 2
    assert by_stage["blueprint"]["calls"] == 1
    assert by_stage["blueprint_repair"]["calls"] == 1
    assert len(client_calls) == 4
    llm_usage.reset()
