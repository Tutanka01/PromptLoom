from __future__ import annotations

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


def test_manim_engine_fps_follows_render_fps() -> None:
    for fps in (30, 60):
        settings = Settings(repo_root=_REPO_ROOT, render_fps=fps)
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
    pipeline._forget_suspect_scene_codes(error)
    error.result = _review()
    pipeline._forget_suspect_scene_codes(error)
    pipeline._forget_suspect_scene_codes(RuntimeError("render failed"))
    assert forgotten == [{"Scene2EN"}, None, None]


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
    remotion = VideoPipeline(Settings(repo_root=_REPO_ROOT, fake_llm=True, render_engine="remotion"))
    assert remotion._start_speculative_render(blueprint, tmp_path, args, "qh", "30") is None
    manim = VideoPipeline(Settings(repo_root=_REPO_ROOT, fake_llm=True, render_engine="manim"))
    assert manim._start_speculative_render(blueprint, tmp_path, ["python"], "qh", "30") is None
    spec = manim._start_speculative_render(blueprint, tmp_path, args, "qh", "30")
    assert spec is not None
    spec.stop()
