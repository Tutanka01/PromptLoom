from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import ValidationError

from video_api import timing
from video_api.config import Settings
from video_api.schemas import BeatSpec, SceneSpec, VideoBlueprint


logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You produce high-quality STEM educational explainer videos.
Return ONLY a single valid JSON object. No prose, no markdown, no code fences.
The JSON must describe a complete 3-5 minute video blueprint by default.
Every scene must have a key like Scene1_HookEN, Scene2_CoreIdeaEN.
For a 3-5 minute target, produce 8 to 12 scenes with enough narration to actually fill the duration.
Each scene must include duration_seconds, one approved visual primitive, narration text, and 5 to 7 concrete beats unless the scene is very short.
Each beat has: at (a ratio), text_hint (the spoken idea), visual_action (an instruction to the renderer), and label.
label is the SHORT on-screen text that will literally be drawn on a card (<= 40 chars, no trailing period, e.g. "average rate", "let h approach 0"). Never put an instruction like "Reveal the card" in label.
Beat at values must be normalized ratios between 0.0 and 1.0 inside that scene, not seconds or global timestamps.
The voice and image must explain the same idea at the same time.
Plan the explanation from intuition, to mechanism, to transfer or recap. Use precise academic language, but introduce terms before relying on them.
You are planning a blueprint; a separate expert step then authors real, bespoke Manim code for each scene (it can use LaTeX equations, plotted axes/graphs, code blocks, labelled diagrams). So describe CONCRETE, topic-specific visuals, and make scenes look different from one another — avoid making every scene a row of generic cards.
The `layout` field is a SUGGESTED composition family, not a hard constraint: pick the closest of
concept_map, process_flow, layered_system, timeline, equation_transform,
graph_plot, comparison_table, cycle_diagram, spatial_model, recap_map.
In `visual_intent` and each beat's `visual_action`, name the actual objects to draw and how they change (e.g. "write the limit definition in LaTeX, then morph the difference quotient into f'(x)", "plot f(x)=x^2 on axes and draw the tangent at x=2", "highlight line 3 of the loop as the counter increments"). One active idea at a time. Never write vague actions like "make it nice"."""


VISUAL_PRIMITIVES = [
    "concept_map",
    "process_flow",
    "layered_system",
    "timeline",
    "equation_transform",
    "graph_plot",
    "comparison_table",
    "cycle_diagram",
    "spatial_model",
    "recap_map",
]

LEGACY_LAYOUT_MAP = {
    "process_pipeline": "process_flow",
    "privilege_boundary": "layered_system",
    "memory_translation": "spatial_model",
    "scheduler_timeline": "timeline",
    "syscall_gate": "process_flow",
    "cpu_registers": "comparison_table",
    "hardware_path": "process_flow",
}

SUBJECT_AREAS = {"math", "physics", "cs", "biology", "chemistry", "engineering", "general_stem"}
DIFFICULTIES = {"intro", "intermediate", "advanced"}
DIFFICULTY_ALIASES = {
    "beginner": "intro",
    "basic": "intro",
    "introductory": "intro",
    "medium": "intermediate",
    "expert": "advanced",
}


_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_SCENE_MAP_KEY_RE = re.compile(r"^Scene(\d+)_([A-Za-z0-9]+)(?:EN)?$")


def _strip_reasoning(text: str) -> str:
    """Remove inline <think>...</think> reasoning some models emit before the answer."""
    return _THINK_BLOCK_RE.sub("", text).strip()


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = _strip_reasoning(text)
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError(
            "LLM response did not contain a JSON object "
            f"(response had {len(text)} chars). "
            "If the model is a reasoning model, set VIDEO_API_LLM_ENABLE_THINKING=0."
        )
    return json.loads(cleaned[start : end + 1])


def _few_shot_example() -> dict:
    """One-shot example for the LLM: a full, rule-compliant 240s blueprint.

    Derived from `fake_blueprint` so the example always satisfies the same
    constraints we ask the model to meet (8 scenes, enough narration to clear the
    duration gate). A short, contradictory example would teach the model to write
    too little narration, which is exactly the failure we are fixing.
    """
    example = fake_blueprint("Explain the derivative in calculus", "math").model_dump()
    example["title"] = "The Derivative: Instant Rate of Change"
    example["slug"] = "derivative-instant-rate"
    example["teaching_goal"] = "Explain derivatives through the shrinking-interval intuition."
    example["learning_objectives"] = [
        "Explain average rate of change with two points.",
        "Show how shrinking the interval produces the derivative.",
        "Connect the tangent slope to the limit definition.",
    ]
    return example


def _load_generation_guidelines(settings: Settings) -> str:
    path = settings.repo_root / "apps" / "video-api" / "docs" / "manim-generation-guidelines.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")[:4000]


def _beat_ratio(index: int, count: int) -> float:
    return round(0.12 + (0.76 * index / max(1, count - 1)), 3)


def _fallback_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return re.sub(r"-+", "-", slug)[:60].strip("-") or "generated-video"


def _normalize_scene_key(value: Any, scene_index: int) -> str:
    raw = str(value or f"Scene{scene_index}_GeneratedEN").strip()
    match = _SCENE_MAP_KEY_RE.match(raw)
    if match:
        suffix = match.group(2)
        return f"Scene{match.group(1)}_{suffix if suffix.endswith('EN') else suffix + 'EN'}"
    return raw


def _scene_sort_key(key: str) -> tuple[int, str]:
    match = _SCENE_MAP_KEY_RE.match(key)
    if match:
        return int(match.group(1)), key
    return 10_000, key


def _scene_map_entries(data: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    entries = [
        (key, value)
        for key, value in data.items()
        if _SCENE_MAP_KEY_RE.match(str(key)) and isinstance(value, dict)
    ]
    return sorted(entries, key=lambda item: _scene_sort_key(item[0]))


def _stringify_style_notes(value: Any) -> Any:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            if isinstance(item, dict):
                rendered = ", ".join(f"{sub_key}={sub_value}" for sub_key, sub_value in item.items())
            elif isinstance(item, list):
                rendered = ", ".join(str(entry) for entry in item)
            else:
                rendered = str(item)
            if rendered.strip():
                parts.append(f"{key}: {rendered}")
        return "; ".join(parts)
    if isinstance(value, list):
        return "; ".join(str(item) for item in value if str(item).strip())
    return value


def _coerce_scene_collection(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    entries = _scene_map_entries(value)
    if not entries:
        return value
    scenes = []
    for index, (key, scene_data) in enumerate(entries, start=1):
        scene = dict(scene_data)
        scene["key"] = _normalize_scene_key(scene.get("key") or key, index)
        scenes.append(scene)
    logger.warning("llm.coerce.scene_dict_to_list scenes=%d", len(scenes))
    return scenes


def _coerce_repaired_blueprint_shape(
    data: Any,
    previous: Any,
    prompt: str,
    target_duration_seconds: int,
) -> Any:
    if not isinstance(data, dict) or "scenes" in data:
        return data
    scene_entries = _scene_map_entries(data)
    if not scene_entries:
        return data

    previous_data = previous if isinstance(previous, dict) else {}
    repaired: dict[str, Any] = {
        "title": data.get("title") or previous_data.get("title") or "Generated Video",
        "theme": data.get("theme") or previous_data.get("theme") or "general_stem",
        "slug": data.get("slug") or previous_data.get("slug") or _fallback_slug(prompt),
        "target_duration_seconds": (
            data.get("target_duration_seconds")
            or previous_data.get("target_duration_seconds")
            or target_duration_seconds
        ),
        "subject_area": data.get("subject_area") or previous_data.get("subject_area") or data.get("theme") or "general_stem",
        "difficulty": data.get("difficulty") or previous_data.get("difficulty") or "intro",
        "audience": data.get("audience") or previous_data.get("audience") or "STEM learners.",
        "teaching_goal": data.get("teaching_goal") or previous_data.get("teaching_goal") or prompt,
        "learning_objectives": (
            data.get("learning_objectives")
            or previous_data.get("learning_objectives")
            or ["Explain the core idea clearly."]
        ),
        "style_notes": (
            data.get("style_notes")
            or previous_data.get("style_notes")
            or "Dark academic style, stable diagrams, clear arrows, one active concept at a time."
        ),
        "scenes": [],
    }
    for index, (key, scene_data) in enumerate(scene_entries, start=1):
        scene = dict(scene_data)
        scene["key"] = _normalize_scene_key(scene.get("key") or key, index)
        repaired["scenes"].append(scene)
    logger.warning(
        "llm.repair.coerced_scene_map scenes=%d had_previous_metadata=%s",
        len(repaired["scenes"]),
        bool(previous_data),
    )
    return repaired


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_absolute_beat_times(beats: list[Any]) -> list[Any]:
    numeric_times = [_float_or_none(beat.get("at")) if isinstance(beat, dict) else None for beat in beats]
    if not any(value is not None and value > 1.0 for value in numeric_times):
        return beats

    known_times = [value for value in numeric_times if value is not None]
    if not known_times:
        return beats

    start = min(known_times)
    end = max(known_times)
    normalized = []
    for beat_index, beat in enumerate(beats):
        if not isinstance(beat, dict):
            normalized.append(beat)
            continue
        beat_item = dict(beat)
        value = numeric_times[beat_index]
        if value is None or end <= start:
            beat_item["at"] = _beat_ratio(beat_index, len(beats))
        else:
            beat_item["at"] = round(0.12 + (0.76 * (value - start) / (end - start)), 3)
        normalized.append(beat_item)
    return normalized


def _normalize_beat_ratios(beats: list[Any]) -> list[Any]:
    """Keep beat timings valid enough for Pydantic without another LLM repair.

    Models often return useful beat text/actions but put the last ratio around
    0.6. That is not worth a full blueprint repair call: redistribute the beat
    timings across the scene while preserving the beat order and content.
    """
    if not beats:
        return beats
    numeric_times = [_float_or_none(beat.get("at")) if isinstance(beat, dict) else None for beat in beats]
    known_times = [value for value in numeric_times if value is not None]
    needs_redistribution = (
        len(known_times) != len(beats)
        or any(value < 0.0 or value > 1.0 for value in known_times)
        or known_times != sorted(known_times)
        or (known_times and known_times[-1] < 0.75)
    )
    if not needs_redistribution:
        return beats

    normalized = []
    for beat_index, beat in enumerate(beats):
        if not isinstance(beat, dict):
            normalized.append(beat)
            continue
        beat_item = dict(beat)
        beat_item["at"] = _beat_ratio(beat_index, len(beats))
        normalized.append(beat_item)
    logger.warning("llm.coerce.redistributed_beats count=%d", len(beats))
    return normalized


def _coerce_blueprint_shape(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    coerced = dict(data)
    coerced["target_duration_seconds"] = coerced.get("target_duration_seconds") or coerced.get("duration_seconds") or 240
    subject_area = (
        coerced.get("subject_area")
        or coerced.get("discipline")
        or coerced.get("domain")
        or coerced.get("theme")
        or "general_stem"
    )
    subject_area = str(subject_area).strip().lower().replace("-", "_")
    coerced["subject_area"] = subject_area if subject_area in SUBJECT_AREAS else "general_stem"
    difficulty = str(coerced.get("difficulty") or coerced.get("level") or "intro").strip().lower()
    difficulty = DIFFICULTY_ALIASES.get(difficulty, difficulty)
    coerced["difficulty"] = difficulty if difficulty in DIFFICULTIES else "intro"
    coerced["learning_objectives"] = (
        coerced.get("learning_objectives")
        or coerced.get("objectives")
        or coerced.get("learning_goals")
        or [coerced.get("teaching_goal") or "Explain the core idea clearly."]
    )
    coerced["style_notes"] = _stringify_style_notes(
        coerced.get("style_notes")
        or coerced.get("visual_style")
        or coerced.get("style")
        or "Dark academic style, stable diagrams, clear arrows, one active concept at a time."
    )
    scenes = _coerce_scene_collection(coerced.get("scenes"))
    coerced["scenes"] = scenes
    if not isinstance(scenes, list):
        return coerced

    normalized_scenes = []
    target_duration = int(coerced.get("target_duration_seconds") or 240)
    default_scene_duration = max(18, round(target_duration / max(1, len(scenes))))
    for scene_index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            normalized_scenes.append(scene)
            continue
        item = dict(scene)
        item["key"] = _normalize_scene_key(item.get("key") or item.get("class"), scene_index)
        item["title"] = item.get("title") or item.get("name") or f"Scene {scene_index}"
        item["text"] = (
            item.get("text")
            or item.get("narration")
            or item.get("voiceover")
            or item.get("script")
            or item.get("spoken_text")
        )
        item["visual_intent"] = (
            item.get("visual_intent")
            or item.get("visual_plan")
            or item.get("visual_description")
            or item.get("visual")
            or item.get("description")
        )
        layout = item.get("layout") or item.get("visual_layout") or item.get("template") or item.get("scene_type")
        mapped_layout = LEGACY_LAYOUT_MAP.get(layout, layout)
        item["layout"] = (
            mapped_layout
            if mapped_layout in VISUAL_PRIMITIVES
            else VISUAL_PRIMITIVES[(scene_index - 1) % len(VISUAL_PRIMITIVES)]
        )
        item["duration_seconds"] = item.get("duration_seconds") or item.get("target_duration_seconds") or default_scene_duration

        beats = item.get("beats") or item.get("visual_beats") or item.get("beat_sync") or []
        normalized_beats = []
        if isinstance(beats, list):
            count = max(1, len(beats))
            for beat_index, beat in enumerate(beats):
                if not isinstance(beat, dict):
                    normalized_beats.append(beat)
                    continue
                beat_item = dict(beat)
                beat_item["key"] = beat_item.get("key") or f"beat_{beat_index + 1}"
                beat_item["at"] = beat_item.get("at", beat_item.get("time", beat_item.get("ratio")))
                if beat_item["at"] is None:
                    beat_item["at"] = _beat_ratio(beat_index, count)
                beat_item["text_hint"] = (
                    beat_item.get("text_hint")
                    or beat_item.get("spoken_idea")
                    or beat_item.get("narration_hint")
                    or beat_item.get("voiceover")
                    or beat_item.get("text")
                )
                beat_item["visual_action"] = (
                    beat_item.get("visual_action")
                    or beat_item.get("visual")
                    or beat_item.get("action")
                    or beat_item.get("animation")
                    or beat_item.get("screen")
                )
                beat_item["label"] = (
                    beat_item.get("label")
                    or beat_item.get("caption")
                    or beat_item.get("on_screen")
                    or beat_item.get("on_screen_text")
                    or ""
                )
                normalized_beats.append(beat_item)
        item["beats"] = _normalize_beat_ratios(_normalize_absolute_beat_times(normalized_beats))
        normalized_scenes.append(item)
    coerced["scenes"] = normalized_scenes
    return coerced


def _ensure_fake_narration_budget(scenes: list[SceneSpec], required_words: int) -> None:
    """Safety net: append topical sentences round-robin until the canned
    narration clears the duration gate for the chosen target. The curated text
    is normally already long enough; this only kicks in for unusual targets."""
    total = sum(timing.word_count(scene.text) for scene in scenes)
    guard = 0
    while total < required_words and guard < len(scenes) * 50:
        scene = scenes[guard % len(scenes)]
        scene.text = (
            f"{scene.text} Keep this in mind: {scene.title.lower()} stays the focus "
            "while the visual updates one step at a time."
        )
        total = sum(timing.word_count(s.text) for s in scenes)
        guard += 1


def fake_blueprint(
    prompt: str,
    theme: str | None = None,
    target_duration_seconds: int | None = None,
) -> VideoBlueprint:
    safe_theme = theme or "general-stem"
    target = int(target_duration_seconds or 240)
    title = "Prompt To Academic Video"
    scene_duration = max(24, round(target / 8))
    academic_scene_data = [
        (
            "Scene1_HookEN",
            "The changing quantity",
            "concept_map",
            "Build a concept map from changing quantities to the question of instant rate.",
            "A derivative begins with a simple question: how fast is something changing right now? Not over a whole trip, not across a long experiment, but at one precise input. The idea matters because many academic models are built from changing quantities: position, temperature, concentration, population, and cost. Each of those quantities can speed up or slow down, and a derivative is the tool that measures that local pace precisely.",
            [
                ("question", 0.10, "how fast is something changing", "Reveal the central question."),
                ("now", 0.30, "right now", "Focus a single input point."),
                ("not_average", 0.48, "not over a whole trip", "Dim a long interval and keep the point highlighted."),
                ("examples", 0.68, "position, temperature, concentration", "Reveal example quantity cards around the central idea."),
                ("purpose", 0.88, "models are built from changing quantities", "Connect the examples back to the derivative."),
            ],
        ),
        (
            "Scene2_MechanismEN",
            "Average rate first",
            "process_flow",
            "Show two points, output change, input change, and the secant slope formula.",
            "The easiest starting point is average rate of change. Pick two inputs, measure the change in output, and divide by the change in input. That gives the slope of a secant line. It is useful, but it still describes an interval, so it cannot yet answer what is happening at exactly one point. Still, the average rate is the honest first step, because the instant rate is defined as its limit.",
            [
                ("two_inputs", 0.12, "Pick two inputs", "Place two input points on a graph."),
                ("output_change", 0.30, "change in output", "Draw a vertical delta output marker."),
                ("input_change", 0.48, "change in input", "Draw a horizontal delta input marker."),
                ("slope", 0.66, "slope of a secant line", "Create the secant line through both points."),
                ("interval", 0.88, "still describes an interval", "Bracket the interval and dim the rest of the graph."),
            ],
        ),
        (
            "Scene3_LimitEN",
            "Shrink the interval",
            "spatial_model",
            "Animate the second point approaching the first until the secant becomes tangent.",
            "To get an instant rate, keep one point fixed and slide the second point closer. The secant line rotates as the interval shrinks. If those slopes settle toward a stable value, that value is the derivative at the fixed point. Visually, the secant has become a tangent. The key intuition is that a smooth curve looks more and more like a straight line as you keep zooming in.",
            [
                ("fixed", 0.10, "keep one point fixed", "Pin the first point on the curve."),
                ("slide", 0.28, "slide the second point closer", "Move the second point toward the first."),
                ("rotate", 0.46, "secant line rotates", "Rotate the secant line as the point moves."),
                ("stable", 0.66, "settle toward a stable value", "Show slope values converging."),
                ("tangent", 0.88, "secant has become a tangent", "Replace the secant with a tangent line."),
            ],
        ),
        (
            "Scene4_EquationEN",
            "The limit formula",
            "equation_transform",
            "Transform average rate notation into the derivative limit definition.",
            "The notation writes that shrinking process as a limit. Start with the difference quotient, f of x plus h minus f of x, divided by h. Then let h approach zero. The formula is not a trick; it is the average rate calculation with the interval pushed as small as the function allows. Read aloud, it simply says: take the average slope, then squeeze the interval toward zero width.",
            [
                ("difference", 0.10, "difference quotient", "Reveal the difference quotient."),
                ("fxh", 0.30, "f of x plus h minus f of x", "Highlight the numerator."),
                ("divide", 0.48, "divided by h", "Highlight the denominator as the input interval."),
                ("limit", 0.68, "let h approach zero", "Add the limit operator."),
                ("meaning", 0.88, "average rate calculation", "Connect the equation back to the shrinking interval."),
            ],
        ),
        (
            "Scene5_GraphEN",
            "Reading slope on a graph",
            "graph_plot",
            "Show tangent slopes at positive, zero, and negative regions of a curve.",
            "On a graph, the derivative is the slope of the tangent line. A positive slope means the output is increasing near that input. A negative slope means it is decreasing. A slope near zero means the graph is locally flat. The derivative turns the shape of a curve into a precise number. The same curve can be rising here and falling there, and the derivative records each of those local behaviours.",
            [
                ("tangent", 0.10, "slope of the tangent line", "Draw a tangent line on the curve."),
                ("positive", 0.30, "positive slope", "Move focus to an increasing region."),
                ("negative", 0.50, "negative slope", "Move focus to a decreasing region."),
                ("zero", 0.70, "slope near zero", "Show a nearly flat tangent at the top."),
                ("number", 0.88, "shape of a curve into a precise number", "Reveal slope value labels."),
            ],
        ),
        (
            "Scene6_UnitsEN",
            "Units keep the meaning",
            "comparison_table",
            "Compare example functions with their derivative units and interpretations.",
            "A derivative also carries units. If position is measured in meters and time is measured in seconds, the derivative has units of meters per second. If cost is measured in dollars and output in units produced, the derivative is dollars per unit. The units tell you what kind of rate the number represents. Carrying units along is what turns an abstract slope into a physically meaningful rate you can reason about.",
            [
                ("units", 0.10, "carries units", "Reveal a units comparison table."),
                ("position", 0.30, "meters and seconds", "Highlight the position over time row."),
                ("velocity", 0.48, "meters per second", "Transform the units into meters per second."),
                ("cost", 0.68, "dollars per unit", "Highlight the cost example row."),
                ("meaning", 0.88, "what kind of rate", "Focus the interpretation column."),
            ],
        ),
        (
            "Scene7_WhenItFailsEN",
            "When the derivative fails",
            "cycle_diagram",
            "Cycle through corner, jump, and vertical tangent failure modes.",
            "The derivative exists only when the limiting slope settles down. At a sharp corner, the slope from the left and the slope from the right can disagree. At a jump, the graph does not connect smoothly. At a vertical tangent, the slope can grow without bound. These are not exceptions to memorize; they are cases where the tangent idea breaks. Recognising them early tells you when a smooth-rate model is simply the wrong tool for the data.",
            [
                ("settles", 0.10, "limiting slope settles down", "Show the stable-slope condition."),
                ("corner", 0.30, "sharp corner", "Reveal a corner case."),
                ("jump", 0.50, "At a jump", "Move to a discontinuous jump case."),
                ("vertical", 0.70, "vertical tangent", "Move to a vertical tangent case."),
                ("breaks", 0.88, "tangent idea breaks", "Summarize why each case fails."),
            ],
        ),
        (
            "Scene8_RecapEN",
            "The takeaway",
            "recap_map",
            "Summarize average rate, limit, tangent slope, and academic applications.",
            "The useful mental model is compact: average rate uses two points, the derivative pushes the second point toward the first, and the result is the tangent slope if the limit exists. That single idea connects motion, growth, optimization, and many scientific models. The symbols matter because they preserve the shrinking-interval story. Hold onto that picture, and every later rule of differentiation becomes a shortcut for the same limit.",
            [
                ("average", 0.14, "average rate uses two points", "Show the two-point summary."),
                ("limit", 0.34, "pushes the second point", "Show the limiting process."),
                ("tangent", 0.56, "tangent slope", "Reveal the tangent slope result."),
                ("applications", 0.74, "motion, growth, optimization", "Reveal application cards."),
                ("symbols", 0.88, "shrinking-interval story", "Connect the formula back to the visual story."),
            ],
        ),
    ]
    scenes = [
        SceneSpec(
            key=key,
            title=scene_title,
            duration_seconds=scene_duration,
            layout=layout,
            visual_intent=visual_intent,
            text=text,
            beats=[
                BeatSpec(key=beat_key, at=at, text_hint=text_hint, visual_action=visual_action)
                for beat_key, at, text_hint, visual_action in beats
            ],
        )
        for key, scene_title, layout, visual_intent, text, beats in academic_scene_data
    ]
    required_words = timing.required_total_words(target)
    if target < 180:
        # Short video: keep just enough scenes (>= 3) to cover the narration
        # budget, then size each scene's planned duration to the target window.
        kept: list[SceneSpec] = []
        words = 0
        for scene in scenes:
            kept.append(scene)
            words += timing.word_count(scene.text)
            if len(kept) >= 3 and words >= required_words:
                break
        scenes = kept
        short_duration = min(75, max(15, round(target / len(scenes))))
        for scene in scenes:
            scene.duration_seconds = short_duration
    _ensure_fake_narration_budget(scenes, required_words)
    return VideoBlueprint(
        title=title,
        theme=safe_theme,
        slug="prompt-to-academic-video",
        target_duration_seconds=target,
        subject_area="math",
        difficulty="intro",
        audience="STEM learners who need a visual, step-by-step explanation.",
        teaching_goal=f"Answer the user prompt with a concise academic explanation: {prompt[:180]}",
        learning_objectives=[
            "Explain the core concept through a concrete visual model.",
            "Connect notation or terminology to the underlying mechanism.",
            "Summarize when the idea applies and where it can fail.",
        ],
        style_notes="Dark academic visual style, stable diagrams, clear arrows, one active concept at a time.",
        scenes=scenes,
    )

class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _build_client(self) -> Any:
        from openai import OpenAI

        return OpenAI(
            api_key=self.settings.openai_api_key,
            base_url=self.settings.openai_base_url,
            timeout=self.settings.llm_timeout_seconds,
            max_retries=self.settings.llm_max_retries,
        )

    def _extra_body(self) -> dict[str, Any]:
        """Vendor-specific knobs. Disable hidden reasoning for vLLM/Qwen-style endpoints
        so the whole token/time budget goes to the JSON answer, not to a <think> block."""
        if self.settings.llm_enable_thinking:
            return {}
        return {"chat_template_kwargs": {"enable_thinking": False}}

    def _complete(self, client: Any, messages: list[dict], *, temperature: float, json_mode: bool) -> str:
        kwargs: dict[str, Any] = {}
        if json_mode and self.settings.llm_response_format == "json_object":
            kwargs["response_format"] = {"type": "json_object"}
        extra_body = self._extra_body()
        if extra_body:
            kwargs["extra_body"] = extra_body
        response = client.chat.completions.create(
            model=self.settings.openai_model,
            temperature=temperature,
            max_tokens=self.settings.llm_max_tokens,
            messages=messages,
            **kwargs,
        )
        content = response.choices[0].message.content or ""
        if not content.strip():
            finish = response.choices[0].finish_reason
            raise ValueError(
                f"LLM returned empty content (finish_reason={finish}). "
                "This usually means a reasoning model exhausted its budget thinking; "
                "set VIDEO_API_LLM_ENABLE_THINKING=0 or raise VIDEO_API_LLM_MAX_TOKENS."
            )
        return content

    def _duration_policy(self, target: int) -> dict[str, Any]:
        """Concrete, numeric narration budget so the model writes enough spoken
        text to clear the final duration gate (verify_mp4) instead of a vague
        'fill the duration' instruction. Mirrors video_api.timing."""
        min_seconds = timing.minimum_final_duration(target, self.settings.default_min_duration_seconds)
        min_total_words = timing.required_total_words(target, self.settings.default_min_duration_seconds)
        scene_count = 8 if target >= 180 else max(3, round(target / 30))
        words_per_scene = max(40, round(min_total_words / scene_count))
        return {
            "target_seconds": target,
            "minimum_rendered_seconds": min_seconds,
            "speaking_rate_wpm": timing.ESTIMATION_WPM,
            "min_total_narration_words": min_total_words,
            "min_words_per_scene": words_per_scene,
            "for_180_to_300_second_targets": "Use 8 to 12 scenes, each around 20 to 40 seconds.",
            "narration": (
                f"The rendered video is rejected below {min_seconds}s. The spoken narration "
                f"alone must total at least {min_total_words} words (counted across every "
                f"scene's 'text'), roughly {words_per_scene}+ words per scene. Write full "
                "explanatory sentences, not short summaries or bullet labels."
            ),
        }

    def generate_blueprint(
        self,
        prompt: str,
        theme: str | None,
        target_duration_seconds: int | None,
    ) -> VideoBlueprint:
        effective_target = target_duration_seconds or self.settings.default_target_duration_seconds
        if self.settings.fake_llm:
            logger.info("llm.fake_blueprint.start prompt_chars=%d theme=%s", len(prompt), theme)
            return fake_blueprint(prompt, theme, effective_target)

        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required unless VIDEO_API_FAKE_LLM=1")
        try:
            client = self._build_client()
        except ImportError as exc:
            raise RuntimeError("The openai package is required for LLM generation") from exc

        logger.info(
            "llm.request.start model=%s base_url=%s prompt_chars=%d theme=%s thinking=%s",
            self.settings.openai_model,
            self.settings.openai_base_url,
            len(prompt),
            theme,
            self.settings.llm_enable_thinking,
        )
        user_prompt = {
            "prompt": prompt,
            "theme": theme or "general-stem",
            "target_duration_seconds": effective_target,
            "generation_guidelines": _load_generation_guidelines(self.settings),
            "duration_policy": self._duration_policy(effective_target),
            "approved_visual_primitives": VISUAL_PRIMITIVES,
            "required_schema": {
                "title": "string",
                "theme": "kebab-case string",
                "slug": "lowercase kebab-case string",
                "target_duration_seconds": effective_target,
                "subject_area": "math | physics | cs | biology | chemistry | engineering | general_stem",
                "difficulty": "intro | intermediate | advanced",
                "audience": "string",
                "teaching_goal": "string",
                "learning_objectives": ["1 to 5 concise learning objectives"],
                "style_notes": "string",
                "scenes": [
                    {
                        "key": "Scene1_HookEN",
                        "title": "string",
                        "duration_seconds": "integer planned duration for this scene",
                        "layout": "one approved visual primitive string",
                        "text": "English narration for this scene",
                        "visual_intent": "concrete visual plan",
                        "beats": [
                            {
                                "key": "short_identifier",
                                "at": 0.1,
                                "text_hint": "spoken idea around this moment",
                                "label": "short on-screen text (<= 40 chars)",
                                "visual_action": "exact visual action / instruction",
                            }
                        ],
                    }
                ],
            },
        }
        few_shot_request = {
            "prompt": "Explain the derivative in calculus",
            "theme": "math",
            "target_duration_seconds": 240,
        }
        content = self._complete(
            client,
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(few_shot_request, ensure_ascii=True)},
                {"role": "assistant", "content": json.dumps(_few_shot_example(), ensure_ascii=True)},
                {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=True)},
            ],
            temperature=self.settings.llm_temperature,
            json_mode=True,
        )
        logger.info("llm.request.done model=%s response_chars=%d", self.settings.openai_model, len(content))
        data = _coerce_blueprint_shape(_extract_json_object(content))
        try:
            return VideoBlueprint.model_validate(data)
        except ValidationError as exc:
            logger.warning("llm.blueprint.invalid errors=%s", exc)
            repaired = self.repair_blueprint(prompt, data, str(exc))
            return repaired

    def repair_blueprint(self, prompt: str, previous: Any, error_report: str) -> VideoBlueprint:
        if self.settings.fake_llm:
            logger.info("llm.fake_repair.start prompt_chars=%d", len(prompt))
            target = previous.get("target_duration_seconds") if isinstance(previous, dict) else None
            return fake_blueprint(prompt, target_duration_seconds=target)
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for LLM repair")
        client = self._build_client()
        target = None
        if isinstance(previous, dict):
            target = previous.get("target_duration_seconds")
        target = int(target or self.settings.default_target_duration_seconds)
        logger.info(
            "llm.repair.start model=%s base_url=%s error_chars=%d",
            self.settings.openai_model,
            self.settings.openai_base_url,
            len(error_report),
        )
        content = self._complete(
            client,
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task": "Repair this video blueprint JSON so it validates.",
                            "original_prompt": prompt,
                            "previous": previous,
                            "errors": error_report,
                            "generation_guidelines": _load_generation_guidelines(self.settings),
                            "approved_visual_primitives": VISUAL_PRIMITIVES,
                            "duration_policy": self._duration_policy(target),
                            "repair_rules": (
                                "Return the COMPLETE top-level VideoBlueprint object, not a dictionary keyed by scene names. "
                                "Required top-level fields are title, theme, slug, target_duration_seconds, subject_area, "
                                "difficulty, audience, teaching_goal, learning_objectives, style_notes, and scenes. "
                                "Keep target_duration_seconds, use 8-12 scenes for 3-5 minute videos, "
                                "include duration_seconds and an approved visual primitive on every scene. "
                                "If the error mentions narration being too short, LENGTHEN the spoken 'text' of "
                                "scenes until the total word count satisfies duration_policy.min_total_narration_words; "
                                "do not just change field names."
                            ),
                        },
                        ensure_ascii=True,
                    ),
                },
            ],
            temperature=0.15,
            json_mode=True,
        )
        logger.info("llm.repair.done model=%s response_chars=%d", self.settings.openai_model, len(content))
        data = _extract_json_object(content)
        data = _coerce_repaired_blueprint_shape(data, previous, prompt, target)
        return VideoBlueprint.model_validate(_coerce_blueprint_shape(data))
