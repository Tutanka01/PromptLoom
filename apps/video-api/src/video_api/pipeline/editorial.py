"""Editorial artifacts and the pre-render anti-slideshow delivery gate."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from video_api.schemas import ProductionOptions


_MOTION_WEIGHTS = {
    "TitleScene": 0.55,
    "BulletScene": 0.50,
    "FormulaScene": 0.62,
    "CodeScene": 0.76,
    "PlotScene": 0.94,
    "DiagramScene": 0.86,
    "ComparisonScene": 0.70,
    "LayeredSystemScene": 0.74,
    "TimelineScene": 0.82,
    "TerminalScene": 0.82,
    "MemoryScene": 0.78,
    "FlowScene": 0.96,
    "BarChartScene": 0.88,
    "CounterScene": 0.72,
    "ImageScene": 0.72,
    "FootageScene": 1.0,
    "Custom": 0.88,
}
_TEXT_DOMINANT = {"TitleScene", "BulletScene", "FormulaScene", "CounterScene"}


class MotionQualityError(RuntimeError):
    """A structured pre-render rejection that the repair LLM can act on."""

    def __init__(self, report: dict[str, Any]) -> None:
        self.report = report
        blockers = list(report.get("blocking_issues") or report.get("issues") or [])
        super().__init__(
            "delivery promise rejected before render: "
            f"score={report.get('score')}/{report.get('minimum_score')}; "
            + "; ".join(blockers)
        )

    def repair_hint(self) -> str:
        """Return the complete machine-readable evidence, not a vague sentence."""
        return (
            "MotionQualityError: repair the cinematic component mix while preserving the "
            "teaching sequence and already-valid narration. The previous plan was rejected. "
            "Return a materially changed component mix and satisfy every blocking issue. "
            "Full motion report: "
            + json.dumps(self.report, ensure_ascii=False, sort_keys=True)
        )


def evaluate_motion_plan(blueprint: Any, options: ProductionOptions) -> dict[str, Any]:
    scenes = list(blueprint.scenes)
    components = [str(getattr(scene, "component", getattr(scene, "layout", "Custom"))) for scene in scenes]
    count = max(1, len(scenes))
    motion_coverage = sum(_MOTION_WEIGHTS.get(component, 0.75) for component in components) / count
    repeated_ratio = max(Counter(components).values(), default=0) / count
    text_ratio = sum(component in _TEXT_DOMINANT for component in components) / count
    beat_coverage = sum(bool(getattr(scene, "beats", None)) for scene in scenes) / count
    source_coverage = sum(bool(getattr(scene, "source_ids", None)) for scene in scenes) / count
    media_ratio = sum(component in {"ImageScene", "FootageScene"} for component in components) / count

    score = 100.0 * (
        motion_coverage * 0.45
        + (1.0 - repeated_ratio) * 0.20
        + (1.0 - min(1.0, text_ratio)) * 0.15
        + beat_coverage * 0.15
        + min(1.0, source_coverage + (0.25 if not options.research.enabled else 0.0)) * 0.05
    )
    minimum = {"technical": 52.0, "editorial": 64.0, "cinematic": 72.0}[options.mode]
    blocking_issues: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []
    if motion_coverage < 0.68 and options.mode != "technical":
        blocking_issues.append("planned motion coverage is too low")
        recommendations.append(
            "replace text-led scenes with topic-specific FlowScene, DiagramScene, "
            "TimelineScene, PlotScene, or a justified media scene"
        )
    if repeated_ratio > 0.45:
        blocking_issues.append("one scene component dominates the video")
        recommendations.append("vary the scene grammar instead of repeating one component")
    if text_ratio > 0.42 and options.mode != "technical":
        blocking_issues.append("too many text-dominant scenes")
        recommendations.append("keep BulletScene for the recap and visualise the other ideas")
    if beat_coverage < 0.75:
        blocking_issues.append("too many scenes lack narration-driven visual beats")
        recommendations.append("add verbatim narration anchors for every multi-item scene")
    if (
        options.mode == "cinematic"
        and media_ratio == 0
        and components.count("Custom") < 2
        and motion_coverage < 0.78
    ):
        # A component-only weight is deliberately not allowed to veto a plan
        # that is already varied, fully beat-synchronised and only marginally
        # below the palette target. The rendered delivery gate remains strict
        # (freeze ratio + longest static stretch), so this avoids a false
        # negative without silently accepting an actual slideshow.
        synchronised_motion_mix = (
            motion_coverage >= 0.73
            and beat_coverage >= 0.90
            and text_ratio <= 0.30
            and repeated_ratio <= 0.40
        )
        message = (
            "cinematic plan has no resolved media or bespoke scenes; it relies on "
            "narration-synchronised palette motion"
        )
        if synchronised_motion_mix:
            warnings.append(message)
        else:
            blocking_issues.append(
                "cinematic mode needs semantically exact media, bespoke motion, or a "
                "stronger narration-synchronised component mix"
            )
            recommendations.append(
                "change the minimum number of low-motion scenes; use licensed media only "
                "when it explains an observable real-world anchor"
            )
    return {
        "delivery_promise": options.delivery_promise,
        "mode": options.mode,
        "score": round(score, 1),
        "minimum_score": minimum,
        "score_passed": score >= minimum,
        "passed": score >= minimum and not blocking_issues,
        "metrics": {
            "motion_coverage": round(motion_coverage, 3),
            "repeated_component_ratio": round(repeated_ratio, 3),
            "text_dominant_ratio": round(text_ratio, 3),
            "beat_coverage": round(beat_coverage, 3),
            "source_coverage": round(source_coverage, 3),
            "media_scene_ratio": round(media_ratio, 3),
        },
        "component_mix": dict(Counter(components)),
        # Keep `issues` as a compatibility alias for existing report clients.
        "issues": blocking_issues,
        "blocking_issues": blocking_issues,
        "warnings": warnings,
        "recommendations": list(dict.fromkeys(recommendations)),
    }


def write_editorial_artifacts(
    workspace: Path,
    blueprint: Any,
    options: ProductionOptions,
    research: Any | None,
    asset_manifest: Any | None,
) -> dict[str, Any]:
    source_count = len(getattr(research, "sources", []) or [])
    proposal = {
        "version": 1,
        "title": blueprint.title,
        "teaching_goal": blueprint.teaching_goal,
        "audience": blueprint.audience,
        "production": options.model_dump(),
        "delivery_promise": options.delivery_promise,
        "source_count": source_count,
        "style_notes": blueprint.style_notes,
        "acceptance": {
            "narration_matches_visuals": True,
            "assets_have_provenance": True,
            "long_static_stretches_rejected": options.mode != "technical",
        },
    }
    scene_plan = {
        "version": 1,
        "scenes": [
            {
                "key": scene.key,
                "title": scene.title,
                "component": getattr(scene, "component", getattr(scene, "layout", "unknown")),
                "duration_seconds": scene.duration_seconds,
                "visual_intent": scene.visual_intent,
                "source_ids": list(getattr(scene, "source_ids", []) or []),
                "beats": [beat.model_dump() for beat in (getattr(scene, "beats", []) or [])],
                "transition": getattr(scene, "transition", "auto"),
            }
            for scene in blueprint.scenes
        ],
    }
    motion = evaluate_motion_plan(blueprint, options)
    (workspace / "proposal.json").write_text(json.dumps(proposal, indent=2) + "\n", encoding="utf-8")
    (workspace / "scene_plan.json").write_text(json.dumps(scene_plan, indent=2) + "\n", encoding="utf-8")
    (workspace / "motion_plan_report.json").write_text(json.dumps(motion, indent=2) + "\n", encoding="utf-8")
    return motion


def evaluate_rendered_delivery(motion_plan: dict[str, Any], final_report: dict[str, Any]) -> dict[str, Any]:
    freeze = final_report.get("freezedetect") or {}
    duration = max(0.001, float(final_report.get("duration") or 0.001))
    frozen_ratio = float(freeze.get("total") or 0.0) / duration
    longest = float(freeze.get("longest") or 0.0)
    mode = str(motion_plan.get("mode") or "technical")
    max_ratio = {"technical": 0.50, "editorial": 0.28, "cinematic": 0.18}.get(mode, 0.5)
    max_longest = {"technical": 12.0, "editorial": 8.0, "cinematic": 6.0}.get(mode, 12.0)
    passed = bool(motion_plan.get("passed")) and frozen_ratio <= max_ratio and longest <= max_longest
    return {
        "promise": motion_plan.get("delivery_promise"),
        "passed": passed,
        "planned_score": motion_plan.get("score"),
        "frozen_ratio": round(frozen_ratio, 3),
        "longest_static_seconds": round(longest, 3),
        "limits": {"max_frozen_ratio": max_ratio, "max_static_seconds": max_longest},
    }
