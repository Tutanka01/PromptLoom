from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

from video_api.config import Settings
from video_api.pipeline.commands import CommandRunner
from video_api.pipeline.verify import extract_frame
from video_api.schemas import (
    SceneVisualScore,
    VisualIssue,
    VisualReviewResult,
    _DIMENSION_WEIGHTS,
)
from video_api.schemas import VideoBlueprint


logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """\
You are a demanding educational-video quality reviewer with expertise in Manim animations.
Your role is to evaluate rendered video frames against narration context and identify visual problems.

For each scene provided, you receive:
- The scene's narration (what is being spoken)
- The visual_intent (what the animation should show)
- The active beat around the scene midpoint (the specific visual action expected)
- THREE PNG frames extracted at ~20%, ~55% and ~85% of the scene: early (layout settling in),
  mid (the scene's richest state) and late (final state, earlier items may be dimmed).
  Score the scene considering all three: items should accumulate across frames (a static
  scene where the three frames are identical scores low on narration_match), and every
  frame must stay readable and in-frame.

Score each scene on FIVE dimensions, each from 0 to 10:

1. narration_match (weight 0.35): Does the image show what the narration is describing at this moment?
   A score of 10 means the visual perfectly illustrates the spoken idea.
   A score of 0 means the image contradicts or is completely unrelated to the narration.

2. readability (weight 0.20): Are all text labels fully visible, not clipped, legible, and appropriately sized?
   A score of 10 means all text is clear and complete.
   A score of 0 means text is cut off, overlapping, or unreadable.

3. framing (weight 0.20): Are all elements within the frame boundaries, with no overlapping or misaligned elements?
   A score of 10 means clean layout, nothing out of bounds.
   A score of 0 means major layout issues.

4. density (weight 0.15): Is the scene focused on one active idea at a time, without visual clutter?
   A score of 10 means clean, minimal, one concept visible.
   A score of 0 means the frame is overcrowded or confusing.

5. not_blank (weight 0.10): Is meaningful content visible? The screen should not be empty or frozen.
   A score of 10 means rich, relevant content. A score of 0 means empty or all-black screen.

For each ISSUE you identify, report:
- scene_key: the scene identifier
- dimension: which dimension is affected
- severity: "blocker" (text clipped, blank screen, or image contradicts narration), "major" (significant problem), or "minor" (small imperfection)
- message: concise description of the problem
- suggestion: a concrete fix for the blueprint (beat, visual_intent, or narration adjustment)

Return ONLY a valid JSON object with this exact structure:
{
  "scene_scores": [
    {
      "scene_key": "Scene1_HookEN",
      "dimensions": {
        "narration_match": 8,
        "readability": 9,
        "framing": 10,
        "density": 7,
        "not_blank": 10
      }
    }
  ],
  "issues": [
    {
      "scene_key": "Scene1_HookEN",
      "dimension": "readability",
      "severity": "major",
      "message": "The label on the right card is clipped at the edge",
      "suggestion": "Shorten the label to under 35 characters or reduce font size"
    }
  ],
  "summary": "Overall the video is clear but scene 3 has a significant narration mismatch."
}
"""


def _encode_image(path: Path) -> str:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


# Sample each scene early (layout), mid (richest state) and late (final state +
# dim) — one midpoint frame is blind to a scene that starts broken or dies early.
SAMPLE_RATIOS = (0.2, 0.55, 0.85)


def _scene_midpoints(
    blueprint: VideoBlueprint, durations_path: Path
) -> tuple[list[tuple[Any, float]], float]:
    """Return ([(SceneSpec, global_midpoint_seconds)], total_seconds) in scene order.

    Uses actual audio durations when available; falls back to blueprint.duration_seconds.
    The total is derived from the SAME source as the midpoints so callers can clamp
    timestamps against a consistent duration (planned and actual durations differ).
    """
    durations: dict[str, float] = {}
    if durations_path.exists():
        try:
            durations = json.loads(durations_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    midpoints: list[tuple[Any, float]] = []
    cumulative = 0.0
    for scene in blueprint.scenes:
        dur = float(durations.get(scene.key, scene.duration_seconds))
        midpoints.append((scene, cumulative + dur / 2.0))
        cumulative += dur
    return midpoints, cumulative


def _scene_sample_points(
    blueprint: VideoBlueprint, durations_path: Path
) -> tuple[list[tuple[Any, list[float]]], float]:
    """Return ([(scene, [t_early, t_mid, t_late])], total_seconds) in scene order."""
    durations: dict[str, float] = {}
    if durations_path.exists():
        try:
            durations = json.loads(durations_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    samples: list[tuple[Any, list[float]]] = []
    cumulative = 0.0
    for scene in blueprint.scenes:
        dur = float(durations.get(scene.key, scene.duration_seconds))
        samples.append((scene, [cumulative + dur * ratio for ratio in SAMPLE_RATIOS]))
        cumulative += dur
    return samples, cumulative


def _active_beat(scene: Any, ratio: float = 0.5) -> dict:
    """Return the beat whose `at` is closest to the given ratio within a scene.

    Remotion scenes carry no beats; synthesize one from the visual intent so the
    review works uniformly across engines.
    """
    beats = getattr(scene, "beats", None) or []
    if not beats:
        intent = getattr(scene, "visual_intent", "") or scene.text[:160]
        return {"key": "mid", "at": ratio, "text_hint": intent, "visual_action": intent}
    best = min(beats, key=lambda b: abs(b.at - ratio))
    return {
        "key": best.key,
        "at": best.at,
        "text_hint": best.text_hint,
        "visual_action": best.visual_action,
    }


def _compute_score(dimensions: dict[str, float]) -> float:
    total = sum(
        _DIMENSION_WEIGHTS.get(dim, 0.0) * clamp(val)
        for dim, val in dimensions.items()
    )
    return round(total * 10.0, 2)


def clamp(val: float, lo: float = 0.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, float(val)))


def _parse_review_response(raw: dict, scene_midpoints: list[tuple[Any, float]], min_score: float) -> VisualReviewResult:
    """Convert raw LLM JSON into a VisualReviewResult with deterministic scoring."""
    scene_scores: list[SceneVisualScore] = []
    lm_scene_map = {entry["scene_key"]: entry for entry in raw.get("scene_scores", []) if "scene_key" in entry}

    for scene, ts in scene_midpoints:
        entry = lm_scene_map.get(scene.key, {})
        raw_dims = entry.get("dimensions", {})
        # Fill any missing dimensions with 5 (neutral) so score is never undefined
        dims = {dim: clamp(float(raw_dims.get(dim, 5))) for dim in _DIMENSION_WEIGHTS}
        score = _compute_score(dims)
        scene_scores.append(SceneVisualScore(
            scene_key=scene.key,
            timestamp=round(ts, 3),
            dimensions=dims,
            score=score,
        ))

    global_score = round(sum(s.score for s in scene_scores) / max(len(scene_scores), 1), 2)

    issues: list[VisualIssue] = []
    for raw_issue in raw.get("issues", []):
        # Normalize the severity: an unknown value (e.g. "critical", "high") must not be
        # silently dropped — surface it as "major" so a flagged problem still counts.
        sev = str(raw_issue.get("severity", "minor")).strip().lower()
        if sev not in ("blocker", "major", "minor"):
            sev = "major"
        try:
            issues.append(VisualIssue(
                scene_key=str(raw_issue.get("scene_key", "unknown")),
                dimension=str(raw_issue.get("dimension", "unknown")),
                severity=sev,  # type: ignore[arg-type]
                message=str(raw_issue.get("message", "")),
                suggestion=str(raw_issue.get("suggestion", "")),
            ))
        except Exception:
            pass

    has_blocker = any(i.severity == "blocker" for i in issues)
    passed = (global_score >= min_score) and not has_blocker

    return VisualReviewResult(
        score=global_score,
        passed=passed,
        scene_scores=scene_scores,
        issues=issues,
        summary=raw.get("summary", ""),
    )


class VisualReviewer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError("openai package required for visual review") from exc
            self._client = OpenAI(
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                timeout=self.settings.llm_timeout_seconds,
            )
        return self._client

    def _model(self) -> str:
        return self.settings.visual_review_model or self.settings.openai_model

    def review(
        self,
        blueprint: VideoBlueprint,
        video_path: Path,
        runner: CommandRunner,
        report_dir: Path,
    ) -> VisualReviewResult:
        """Extract three frames per scene (early/mid/late) and ask a vision model to review them.

        Returns a VisualReviewResult with weighted scores and a pass/fail decision.
        """
        from video_api.pipeline.llm import _extract_json_object  # local import to avoid circular

        video_dir = video_path.parent.parent  # video_path = .../final/<slug>-en-final.mp4
        durations_path = video_dir / "audio" / "en" / "durations.json"
        samples, total_duration = _scene_sample_points(blueprint, durations_path)
        midpoints = [(scene, points[1]) for scene, points in samples]

        vision_dir = report_dir / "vision"
        vision_dir.mkdir(parents=True, exist_ok=True)

        # Build scene context list and extract the frames per scene
        stage_names = ("early", "mid", "late")
        scene_contexts: list[dict] = []
        scene_frames: list[list[Path | None]] = []

        for scene, points in samples:
            frames: list[Path | None] = []
            for stage, ts in zip(stage_names, points):
                safe_ts = min(ts, total_duration - 0.1) if total_duration > 0.1 else ts
                frame_out = vision_dir / f"{scene.key}_{stage}.png"
                try:
                    extract_frame(runner, video_path, safe_ts, frame_out)
                    frames.append(frame_out)
                except Exception as exc:
                    logger.warning(
                        "vision.frame_extraction.failed scene=%s stage=%s ts=%.3f error=%s",
                        scene.key, stage, ts, exc,
                    )
                    frames.append(None)
            scene_frames.append(frames)

            scene_contexts.append({
                "scene_key": scene.key,
                "narration": scene.text,
                "visual_intent": scene.visual_intent,
                "active_beat": _active_beat(scene),
                "frame_timestamps_seconds": [round(ts, 2) for ts in points],
            })
            logger.info(
                "vision.frames.ready scene=%s frames=%d", scene.key,
                sum(1 for f in frames if f is not None),
            )

        # Build multimodal message: text rubric + three images per scene (in order)
        content: list[dict] = [
            {
                "type": "text",
                "text": (
                    f"Review {len(samples)} scenes from an educational video.\n"
                    f"Each scene has THREE frames below (early/mid/late), in scene order.\n\n"
                    f"Scene contexts (JSON):\n{json.dumps(scene_contexts, indent=2, ensure_ascii=True)}\n\n"
                    "Images follow grouped per scene. Score each scene on the 5 dimensions described in your instructions."
                ),
            }
        ]
        for frames, (scene, _) in zip(scene_frames, samples):
            for stage, frame_path in zip(stage_names, frames):
                content.append({"type": "text", "text": f"Scene {scene.key} — {stage} frame:"})
                if frame_path is not None and frame_path.exists():
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": _encode_image(frame_path)},
                    })
                else:
                    content.append({"type": "text", "text": "(frame extraction failed — treat not_blank as 0)"})

        logger.info(
            "vision.review.start model=%s scenes=%d frames=%d",
            self._model(),
            len(samples),
            sum(len([f for f in frames if f]) for frames in scene_frames),
        )

        client = self._get_client()
        response = client.chat.completions.create(
            model=self._model(),
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            response_format={"type": "json_object"},
            max_tokens=self.settings.visual_review_max_tokens,
        )
        raw_text = response.choices[0].message.content or ""
        raw_json = _extract_json_object(raw_text)

        result = _parse_review_response(raw_json, midpoints, self.settings.visual_review_min_score)

        blockers = sum(1 for i in result.issues if i.severity == "blocker")
        logger.info(
            "vision.review.done model=%s scenes=%d score=%.1f passed=%s blockers=%d",
            self._model(),
            len(midpoints),
            result.score,
            result.passed,
            blockers,
        )
        return result
