from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import ValidationError

from video_api.config import Settings
from video_api.schemas import BeatSpec, SceneSpec, VideoBlueprint, _short_label


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
Do not request raw Python Manim. Plan with this deterministic visual grammar only:
concept_map, process_flow, layered_system, timeline, equation_transform,
graph_plot, comparison_table, cycle_diagram, spatial_model, recap_map.
Good Manim scenes use explicit Mobjects, stable positioning, transforms, movement, focus/dim,
and one active idea at a time. Avoid generic "make it nice" visual actions."""


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
    """Return a compact 4-scene blueprint dict to use as a one-shot example for the LLM."""
    example = _few_shot_example_raw()
    for scene in example["scenes"]:
        for beat in scene["beats"]:
            beat["label"] = _short_label(beat["text_hint"])
    return example


def _few_shot_example_raw() -> dict:
    return {
        "title": "The Derivative: Instant Rate of Change",
        "theme": "math",
        "slug": "derivative-instant-rate",
        "target_duration_seconds": 240,
        "subject_area": "math",
        "difficulty": "intro",
        "audience": "STEM learners who need a visual, step-by-step explanation.",
        "teaching_goal": "Explain derivatives through the shrinking-interval intuition.",
        "learning_objectives": [
            "Explain average rate of change with two points.",
            "Show how shrinking the interval produces the derivative.",
            "Connect the tangent slope to the limit definition.",
        ],
        "style_notes": "Dark academic style, stable diagrams, one active idea at a time.",
        "scenes": [
            {
                "key": "Scene1_HookEN",
                "title": "The changing quantity",
                "duration_seconds": 30,
                "layout": "concept_map",
                "text": "A derivative begins with a simple question: how fast is something changing right now? Not over a whole trip, not across a long experiment, but at one precise input. The idea matters because many academic models are built from changing quantities: position, temperature, concentration, population, and cost.",
                "visual_intent": "Build a concept map from changing quantities to the question of instant rate.",
                "beats": [
                    {"key": "question", "at": 0.10, "text_hint": "how fast is something changing", "visual_action": "Reveal the central question card."},
                    {"key": "now", "at": 0.30, "text_hint": "right now", "visual_action": "Focus a single input point."},
                    {"key": "not_average", "at": 0.48, "text_hint": "not over a whole trip", "visual_action": "Dim a long interval, keep the point highlighted."},
                    {"key": "examples", "at": 0.68, "text_hint": "position, temperature, concentration", "visual_action": "Reveal example quantity cards around the central idea."},
                    {"key": "purpose", "at": 0.88, "text_hint": "models are built from changing quantities", "visual_action": "Connect examples back to the derivative."},
                ],
            },
            {
                "key": "Scene2_MechanismEN",
                "title": "Average rate first",
                "duration_seconds": 30,
                "layout": "process_flow",
                "text": "The easiest starting point is average rate of change. Pick two inputs, measure the change in output, and divide by the change in input. That gives the slope of a secant line. It is useful, but it still describes an interval, so it cannot yet answer what is happening at exactly one point.",
                "visual_intent": "Show two points, output change, input change, and the secant slope formula.",
                "beats": [
                    {"key": "two_inputs", "at": 0.12, "text_hint": "Pick two inputs", "visual_action": "Place two input points on a graph."},
                    {"key": "output_change", "at": 0.30, "text_hint": "change in output", "visual_action": "Draw a vertical delta-output marker."},
                    {"key": "input_change", "at": 0.48, "text_hint": "change in input", "visual_action": "Draw a horizontal delta-input marker."},
                    {"key": "slope", "at": 0.66, "text_hint": "slope of a secant line", "visual_action": "Create the secant line through both points."},
                    {"key": "interval", "at": 0.88, "text_hint": "still describes an interval", "visual_action": "Bracket the interval and dim the rest of the graph."},
                ],
            },
            {
                "key": "Scene3_LimitEN",
                "title": "Shrink the interval",
                "duration_seconds": 30,
                "layout": "spatial_model",
                "text": "To get an instant rate, keep one point fixed and slide the second point closer. The secant line rotates as the interval shrinks. If those slopes settle toward a stable value, that value is the derivative at the fixed point. Visually, the secant has become a tangent.",
                "visual_intent": "Animate the second point approaching the first until the secant becomes tangent.",
                "beats": [
                    {"key": "fixed", "at": 0.10, "text_hint": "keep one point fixed", "visual_action": "Pin the first point on the curve."},
                    {"key": "slide", "at": 0.28, "text_hint": "slide the second point closer", "visual_action": "Move the second point toward the first."},
                    {"key": "rotate", "at": 0.46, "text_hint": "secant line rotates", "visual_action": "Rotate the secant line as the point moves."},
                    {"key": "stable", "at": 0.66, "text_hint": "settle toward a stable value", "visual_action": "Show slope values converging to a number."},
                    {"key": "tangent", "at": 0.88, "text_hint": "secant has become a tangent", "visual_action": "Replace the secant with a tangent line."},
                ],
            },
            {
                "key": "Scene4_EquationEN",
                "title": "The limit formula",
                "duration_seconds": 30,
                "layout": "equation_transform",
                "text": "The notation writes that shrinking process as a limit. Start with the difference quotient, f of x plus h minus f of x, divided by h. Then let h approach zero. The formula is not a trick; it is the average rate calculation with the interval pushed as small as the function allows.",
                "visual_intent": "Transform average rate notation into the derivative limit definition.",
                "beats": [
                    {"key": "difference", "at": 0.10, "text_hint": "difference quotient", "visual_action": "Reveal the difference quotient card."},
                    {"key": "fxh", "at": 0.30, "text_hint": "f of x plus h minus f of x", "visual_action": "Highlight the numerator."},
                    {"key": "divide", "at": 0.48, "text_hint": "divided by h", "visual_action": "Highlight the denominator as the input interval."},
                    {"key": "limit", "at": 0.68, "text_hint": "let h approach zero", "visual_action": "Add the limit operator to the expression."},
                    {"key": "meaning", "at": 0.88, "text_hint": "average rate calculation", "visual_action": "Connect the equation back to the shrinking interval."},
                ],
            },
        ],
    }


def _load_generation_guidelines(settings: Settings) -> str:
    path = settings.repo_root / "apps" / "video-api" / "docs" / "manim-generation-guidelines.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")[:4000]


def _beat_ratio(index: int, count: int) -> float:
    return round(0.12 + (0.76 * index / max(1, count - 1)), 3)


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
    scenes = coerced.get("scenes")
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
        item["key"] = item.get("key") or item.get("class") or f"Scene{scene_index}_GeneratedEN"
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
        item["beats"] = _normalize_absolute_beat_times(normalized_beats)
        normalized_scenes.append(item)
    coerced["scenes"] = normalized_scenes
    return coerced


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
            "A derivative begins with a simple question: how fast is something changing right now? Not over a whole trip, not across a long experiment, but at one precise input. The idea matters because many academic models are built from changing quantities: position, temperature, concentration, population, and cost.",
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
            "The easiest starting point is average rate of change. Pick two inputs, measure the change in output, and divide by the change in input. That gives the slope of a secant line. It is useful, but it still describes an interval, so it cannot yet answer what is happening at exactly one point.",
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
            "To get an instant rate, keep one point fixed and slide the second point closer. The secant line rotates as the interval shrinks. If those slopes settle toward a stable value, that value is the derivative at the fixed point. Visually, the secant has become a tangent.",
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
            "The notation writes that shrinking process as a limit. Start with the difference quotient, f of x plus h minus f of x, divided by h. Then let h approach zero. The formula is not a trick; it is the average rate calculation with the interval pushed as small as the function allows.",
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
            "On a graph, the derivative is the slope of the tangent line. A positive slope means the output is increasing near that input. A negative slope means it is decreasing. A slope near zero means the graph is locally flat. The derivative turns the shape of a curve into a precise number.",
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
            "A derivative also carries units. If position is measured in meters and time is measured in seconds, the derivative has units of meters per second. If cost is measured in dollars and output in units produced, the derivative is dollars per unit. The units tell you what kind of rate the number represents.",
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
            "The derivative exists only when the limiting slope settles down. At a sharp corner, the slope from the left and the slope from the right can disagree. At a jump, the graph does not connect smoothly. At a vertical tangent, the slope can grow without bound. These are not exceptions to memorize; they are cases where the tangent idea breaks.",
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
            "The useful mental model is compact: average rate uses two points, the derivative pushes the second point toward the first, and the result is the tangent slope if the limit exists. That single idea connects motion, growth, optimization, and many scientific models. The symbols matter because they preserve the shrinking-interval story.",
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
    if target < 180:
        short_duration = max(15, round(target / 3))
        scenes = scenes[:3]
        for scene in scenes:
            scene.duration_seconds = short_duration
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
            "duration_policy": {
                "default_target_seconds": self.settings.default_target_duration_seconds,
                "default_min_seconds": self.settings.default_min_duration_seconds,
                "for_180_to_300_second_targets": "Use 8 to 12 scenes, each around 20 to 40 seconds.",
                "narration": "Write enough spoken narration to fill the target duration; avoid short summaries.",
            },
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
                            "repair_rules": (
                                "Keep target_duration_seconds, use 8-12 scenes for 3-5 minute videos, "
                                "include duration_seconds and an approved visual primitive on every scene, and write "
                                "enough narration to satisfy the duration target."
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
        return VideoBlueprint.model_validate(_coerce_blueprint_shape(_extract_json_object(content)))
