from __future__ import annotations

import json
from pathlib import Path

import pytest

from video_api.config import Settings
from video_api.pipeline.assets import AssetResolver
from video_api.pipeline.editorial import (
    MotionQualityError,
    evaluate_motion_plan,
    evaluate_rendered_delivery,
)
from video_api.pipeline.research import Researcher, _normalise_sources, _search_query
from video_api.pipeline.remotion_blueprint import fake_remotion_blueprint, normalize_remotion_blueprint
from video_api.schemas import ProductionOptions


def test_production_options_resolve_advanced_defaults() -> None:
    options = ProductionOptions(mode="cinematic")
    assert options.render_engine == "remotion"
    assert options.research.enabled is True
    assert options.visuals.strategy == "hybrid"
    assert options.visuals.allow_stock is True
    assert options.captions == "full"
    assert options.delivery_promise == "motion_led_explainer"


def test_cinematic_mode_rejects_manim() -> None:
    with pytest.raises(ValueError, match="requires render_engine='remotion'"):
        ProductionOptions(mode="cinematic", render_engine="manim")


def test_fake_research_writes_stable_source_ids() -> None:
    dossier = Researcher(Settings(fake_llm=True)).research("Explain page tables", 10)
    assert dossier.sources[0].id == "src_01"
    context = dossier.prompt_context()
    assert context["sources"][0]["id"] == "src_01"


def test_research_normalisation_deduplicates_and_rejects_non_http() -> None:
    sources = _normalise_sources(
        [
            {"title": "A", "url": "https://kernel.org/a", "text": "one"},
            {"title": "duplicate", "url": "https://kernel.org/a", "text": "two"},
            {"title": "local", "url": "file:///etc/passwd", "text": "bad"},
            {"title": "B", "url": "https://docs.kernel.org/b", "highlights": ["three"]},
        ],
        "exa",
        10,
    )
    assert [source.id for source in sources] == ["src_01", "src_02"]
    assert sources[1].excerpt == "three"


def test_research_compacts_long_production_brief_to_topic_sentence() -> None:
    prompt = (
        "Explain how a Linux system call crosses the user-kernel privilege boundary. "
        "Create a cinematic video with beautiful transitions, exact Pexels footage, "
        "captions, diagrams, and many additional production instructions. " * 8
    )
    query = _search_query(prompt)

    assert len(query) <= 360
    assert query.startswith("Explain how a Linux system call")
    assert not query.endswith(" ")


def test_media_scene_normalises_query_and_drops_untrusted_src() -> None:
    out = normalize_remotion_blueprint(
        {
            "title": "T",
            "slug": "t",
            "scenes": [
                {
                    "key": "Scene1_MediaEN",
                    "title": "Real machines",
                    "narration": "A sufficiently long narration sentence about real machines and how they support the system being explained today.",
                    "component": "image",
                    "props": {
                        "query": "Linux servers inside a modern data center",
                        "src": "https://untrusted.example/image.jpg",
                    },
                }
            ],
        },
        75,
    )
    scene = out["scenes"][0]
    assert scene["component"] == "ImageScene"
    assert scene["props"]["asset_query"].startswith("Linux servers")
    assert "src" not in scene["props"]


def test_asset_resolver_falls_back_when_provider_is_unavailable(tmp_path: Path) -> None:
    data = fake_remotion_blueprint("Explain page tables", "cs", 240).model_dump()
    data["scenes"][1]["component"] = "ImageScene"
    data["scenes"][1]["props"] = {"asset_query": "a real memory module"}
    from video_api.schemas import RemotionBlueprint

    blueprint = RemotionBlueprint.model_validate(data)
    manifest = AssetResolver(Settings(asset_provider="none")).resolve(
        blueprint, tmp_path, allow_stock=True, max_assets=2
    )
    assert blueprint.scenes[1].component == "BulletScene"
    assert manifest.assets[0].status == "fallback"
    assert (tmp_path / "asset_manifest.json").exists()


def test_motion_gate_scores_varied_fake_blueprint() -> None:
    blueprint = fake_remotion_blueprint(
        "Explain scheduling",
        "cs",
        240,
        production_context={"mode": "editorial"},
    )
    for scene in blueprint.scenes:
        scene.source_ids = ["src_01"]
    report = evaluate_motion_plan(blueprint, ProductionOptions(mode="editorial"))
    assert report["score"] >= report["minimum_score"]
    assert report["metrics"]["repeated_component_ratio"] < 0.5


def test_cinematic_fake_blueprint_meets_motion_promise() -> None:
    blueprint = fake_remotion_blueprint(
        "Explain scheduling",
        "cs",
        240,
        production_context={"mode": "cinematic"},
    )
    for scene in blueprint.scenes:
        scene.source_ids = ["src_01"]
    report = evaluate_motion_plan(blueprint, ProductionOptions(mode="cinematic"))
    assert report["passed"] is True
    assert report["issues"] == []
    assert report["metrics"]["motion_coverage"] >= 0.78


def test_cinematic_borderline_mix_passes_when_fully_cued_and_varied() -> None:
    """Regression for a real syscall plan rejected despite score=80/72.

    Two text-led scenes are acceptable when the remaining sequence is varied,
    strongly animated and every scene is narration-synchronised. The lack of
    resolved media remains visible as a warning and the rendered freeze gate
    still has final authority.
    """
    blueprint = fake_remotion_blueprint(
        "Explain the syscall privilege boundary",
        "cs",
        240,
        production_context={"mode": "cinematic"},
    )
    components = [
        "ComparisonScene",
        "LayeredSystemScene",
        "FlowScene",
        "MemoryScene",
        "BulletScene",
        "DiagramScene",
        "FlowScene",
        "BulletScene",
    ]
    for scene, component in zip(blueprint.scenes, components):
        scene.component = component
        scene.source_ids = ["src_01"]

    report = evaluate_motion_plan(blueprint, ProductionOptions(mode="cinematic"))

    assert report["metrics"]["motion_coverage"] == 0.75
    assert report["score"] == 80.0
    assert report["score_passed"] is True
    assert report["passed"] is True
    assert report["blocking_issues"] == []
    assert report["warnings"]


def test_cinematic_slideshow_still_fails_with_actionable_report() -> None:
    blueprint = fake_remotion_blueprint(
        "Explain scheduling",
        "cs",
        240,
        production_context={"mode": "cinematic"},
    )
    for scene in blueprint.scenes:
        scene.component = "BulletScene"
        scene.beats = []

    report = evaluate_motion_plan(blueprint, ProductionOptions(mode="cinematic"))

    assert report["passed"] is False
    assert report["blocking_issues"]
    assert report["recommendations"]
    error = MotionQualityError(report)
    assert '"component_mix"' in error.repair_hint()
    assert "materially changed component mix" in error.repair_hint()


def test_rendered_delivery_uses_freeze_measurements() -> None:
    plan = {"passed": True, "mode": "cinematic", "delivery_promise": "motion_led_explainer", "score": 85}
    good = evaluate_rendered_delivery(
        plan,
        {"duration": 100, "freezedetect": {"total": 5, "longest": 2}},
    )
    bad = evaluate_rendered_delivery(
        plan,
        {"duration": 100, "freezedetect": {"total": 25, "longest": 9}},
    )
    assert good["passed"] is True
    assert bad["passed"] is False
