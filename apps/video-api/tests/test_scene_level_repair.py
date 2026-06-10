from video_api.config import Settings
from video_api.pipeline.engine import RemotionEngine
from video_api.pipeline.llm import LLMClient
from video_api.pipeline.remotion_blueprint import fake_remotion_blueprint
from video_api.schemas import (
    SceneVisualScore,
    VisualIssue,
    VisualReviewResult,
)


def _engine(monkeypatch) -> RemotionEngine:
    monkeypatch.setenv("VIDEO_API_FAKE_LLM", "1")
    monkeypatch.setenv("VIDEO_API_RENDER_ENGINE", "remotion")
    settings = Settings()
    return RemotionEngine(settings, LLMClient(settings))


def _review(issues: list[VisualIssue], scores: list[SceneVisualScore] | None = None) -> VisualReviewResult:
    return VisualReviewResult(
        score=50.0,
        passed=False,
        scene_scores=scores or [],
        issues=issues,
        summary="",
    )


def test_repair_scenes_targets_flagged_scene(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    blueprint = fake_remotion_blueprint("Explain page tables", "linux-fondamentaux")
    flagged = blueprint.scenes[2].key
    review = _review(
        [
            VisualIssue(
                scene_key=flagged,
                dimension="narration_match",
                severity="blocker",
                message="image unrelated to narration",
                suggestion="show the page table walk",
            )
        ]
    )
    # fake_llm: rewrite returns the blueprint unchanged, but the path proves the
    # feedback was attributable (non-None result = scene-level repair chosen).
    repaired = engine.repair_scenes(blueprint.model_dump(), review)
    assert repaired is not None


def test_repair_scenes_returns_none_without_attributable_feedback(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    blueprint = fake_remotion_blueprint("Explain page tables", "linux-fondamentaux")
    review = _review(
        [
            VisualIssue(
                scene_key="unknown",
                dimension="readability",
                severity="major",
                message="somewhere text is clipped",
            ),
            VisualIssue(
                scene_key="SceneX_NotInBlueprintEN",
                dimension="framing",
                severity="blocker",
                message="ghost scene",
            ),
        ]
    )
    assert engine.repair_scenes(blueprint.model_dump(), review) is None


def test_repair_scenes_picks_up_low_scoring_scene(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    blueprint = fake_remotion_blueprint("Explain page tables", "linux-fondamentaux")
    weak = blueprint.scenes[1].key
    review = _review(
        issues=[],
        scores=[
            SceneVisualScore(scene_key=weak, timestamp=12.0, dimensions={}, score=40.0),
            SceneVisualScore(scene_key=blueprint.scenes[0].key, timestamp=2.0, dimensions={}, score=90.0),
        ],
    )
    assert engine.repair_scenes(blueprint.model_dump(), review) is not None


def test_freeze_fatal_defaults_by_engine(monkeypatch) -> None:
    monkeypatch.delenv("VIDEO_API_FREEZE_FATAL", raising=False)
    monkeypatch.setenv("VIDEO_API_RENDER_ENGINE", "remotion")
    assert Settings().verify_freeze_fatal is True
    monkeypatch.setenv("VIDEO_API_RENDER_ENGINE", "manim")
    assert Settings().verify_freeze_fatal is False
    monkeypatch.setenv("VIDEO_API_FREEZE_FATAL", "0")
    monkeypatch.setenv("VIDEO_API_RENDER_ENGINE", "remotion")
    assert Settings().verify_freeze_fatal is False


def test_vision_auto_enables_with_model(monkeypatch) -> None:
    monkeypatch.delenv("VIDEO_API_VISION_ENABLED", raising=False)
    monkeypatch.delenv("VIDEO_API_VISION_MODEL", raising=False)
    assert Settings().visual_review_enabled is False
    monkeypatch.setenv("VIDEO_API_VISION_MODEL", "qwen2.5-vl")
    assert Settings().visual_review_enabled is True
    monkeypatch.setenv("VIDEO_API_VISION_ENABLED", "0")
    assert Settings().visual_review_enabled is False
