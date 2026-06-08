"""Remotion-engine blueprint: system prompt, prop normalisation, fake builder.

The Remotion path asks the LLM to compose a *fixed, tested* React component
palette (no code) plus an optional ``Custom`` escape hatch (free TSX written
later by the Remotion scene-coder). This module owns:

- ``REMOTION_SYSTEM_PROMPT`` — the contract handed to the model;
- ``normalize_remotion_blueprint`` — coerces common LLM output variants and
  turns ``PlotScene`` ``expr`` strings into sampled ``points`` (sandboxed), so
  the React side stays a dumb renderer;
- ``fake_remotion_blueprint`` — a deterministic, gate-passing blueprint for
  ``VIDEO_API_FAKE_LLM=1`` and tests.

The actual OpenAI call lives on ``LLMClient`` (pipeline/llm.py), which reuses
its client/_complete plumbing and calls into here.
"""
from __future__ import annotations

import logging
import math
import re
from typing import Any

from video_api import timing
from video_api.schemas import REMOTION_PALETTE, RemotionBlueprint

logger = logging.getLogger(__name__)


_ALLOWED_COMPONENTS = set(REMOTION_PALETTE) | {"Custom"}

# Lower-cased aliases the model often emits for component names.
_COMPONENT_ALIASES = {
    "title": "TitleScene",
    "titlescene": "TitleScene",
    "intro": "TitleScene",
    "bullet": "BulletScene",
    "bullets": "BulletScene",
    "bulletscene": "BulletScene",
    "list": "BulletScene",
    "summary": "BulletScene",
    "recap": "BulletScene",
    "formula": "FormulaScene",
    "formulascene": "FormulaScene",
    "equation": "FormulaScene",
    "math": "FormulaScene",
    "code": "CodeScene",
    "codescene": "CodeScene",
    "plot": "PlotScene",
    "plotscene": "PlotScene",
    "graph": "PlotScene",
    "chart": "PlotScene",
    "diagram": "DiagramScene",
    "diagramscene": "DiagramScene",
    "graph_diagram": "DiagramScene",
    "comparison": "ComparisonScene",
    "comparisonscene": "ComparisonScene",
    "compare": "ComparisonScene",
    "comparison_table": "ComparisonScene",
    "table": "ComparisonScene",
    "vs": "ComparisonScene",
    "layered_system": "LayeredSystemScene",
    "layeredsystemscene": "LayeredSystemScene",
    "layers": "LayeredSystemScene",
    "layer": "LayeredSystemScene",
    "stack": "LayeredSystemScene",
    "system_layers": "LayeredSystemScene",
    "timeline": "TimelineScene",
    "timelinescene": "TimelineScene",
    "steps": "TimelineScene",
    "process": "TimelineScene",
    "sequence": "TimelineScene",
    "terminal": "TerminalScene",
    "terminalscene": "TerminalScene",
    "shell": "TerminalScene",
    "cli": "TerminalScene",
    "console": "TerminalScene",
    "command": "TerminalScene",
    "memory": "MemoryScene",
    "memoryscene": "MemoryScene",
    "memorygrid": "MemoryScene",
    "grid": "MemoryScene",
    "registers": "MemoryScene",
    "pagetable": "MemoryScene",
    "page_table": "MemoryScene",
    "flow": "FlowScene",
    "flowscene": "FlowScene",
    "packet": "FlowScene",
    "dataflow": "FlowScene",
    "data_flow": "FlowScene",
    "pipeline": "FlowScene",
    "barchart": "BarChartScene",
    "barchartscene": "BarChartScene",
    "bar": "BarChartScene",
    "bars": "BarChartScene",
    "quantities": "BarChartScene",
    "benchmark": "BarChartScene",
    "counter": "CounterScene",
    "counterscene": "CounterScene",
    "metric": "CounterScene",
    "number": "CounterScene",
    "stat": "CounterScene",
    "custom": "Custom",
    "freeform": "Custom",
    "free": "Custom",
}

_PALETTE_LINE = (
    "- TitleScene:   { title: str, subtitle?: str, accent?: \"#hex\" }  — open a video/section\n"
    "- BulletScene:  { title: str, bullets: [str, ...(2-5)], caption?: str, accent?: \"#hex\" }\n"
    "- FormulaScene: { title: str, formulas: [latex_str, ...(1-3)], caption?: str }\n"
    "      latex example: \"f'(x) = \\\\lim_{h \\\\to 0} \\\\frac{f(x+h)-f(x)}{h}\" (escape backslashes for JSON)\n"
    "- CodeScene:    { title: str, code: \"line1\\nline2\", lang: \"python|c|bash|tsx\", codeTitle?: str, caption?: str }\n"
    "- PlotScene:    { title: str, expr: \"python expr in x, e.g. 0.18*x**2 or sin(x)\",\n"
    "                  xRange: [min,max], yRange: [min,max], sweep?: bool, area?: bool, xLabel?: str, yLabel?: str, caption?: str }\n"
    "- DiagramScene: { title: str,\n"
    "                  nodes: [ {id: str, label: str, x: number(-6..6), y: number(-3..3), color?: \"#hex\"} ],\n"
    "                  edges: [ {from: id, to: id, color?: \"#hex\", label?: str} ], caption?: str }\n"
    "- ComparisonScene: { title: str, left: {label: str, items: [str, ...(2-5)]},\n"
    "                  right: {label: str, items: [str, ...(2-5)]}, caption?: str }  — two columns side by side (user vs kernel, before vs after)\n"
    "- LayeredSystemScene: { title: str, layers: [ {label: str, sub?: str, color?: \"#hex\"}, ...(2-5) ], caption?: str }  — stacked bands top->bottom (e.g. App / System Call / Kernel / Hardware)\n"
    "- TimelineScene: { title: str, steps: [ {label: str, sub?: str}, ...(2-5) ], caption?: str }  — left->right sequence / process / lifecycle\n"
    "- TerminalScene: { title: str, command: str, output?: str, caption?: str }  — a shell command typed out + its output\n"
    "- MemoryScene:  { title: str, cells: [ {label?: str, sub?: str, color?: \"#hex\", highlight?: bool}, ...(up to 12) ], cols?: int(1-6), caption?: str }  — grid of cells: memory, page tables, registers, stack frames\n"
    "- FlowScene:    { title: str, stages: [ {label: str, sub?: str}, ...(2-5) ], caption?: str }  — a packet travels left->right through stages (data flow, a syscall's path)\n"
    "- BarChartScene: { title: str, bars: [ {label: str, value: number, color?: \"#hex\"}, ...(2-6) ], caption?: str }  — quantities / benchmarks / comparisons\n"
    "- CounterScene: { title: str, value: number, prefix?: str, suffix?: str, label?: str, decimals?: int, caption?: str }  — one big animated metric (throughput, size, count)\n"
    "- Custom:       { } — use ONLY when no palette component fits; describe the visual fully in `visual_intent`.\n"
    "      A separate expert step writes bespoke React/Remotion code for it. Prefer palette components."
)

REMOTION_SYSTEM_PROMPT = f"""You are a STEM explainer-video director. Design a short narrated video as STRICT JSON.
The video is rendered by composing a fixed library of tested React (Remotion) scene components — you
choose a component and its props per scene; you do NOT write code.

Return ONLY one JSON object (no prose, no markdown fences) with this shape:
{{
  "title": "short video title",
  "theme": "kebab-case theme",
  "slug": "kebab-case-slug",
  "target_duration_seconds": <int>,
  "subject_area": "math | physics | cs | biology | chemistry | engineering | general_stem",
  "difficulty": "intro | intermediate | advanced",
  "audience": "who this is for",
  "teaching_goal": "one sentence",
  "learning_objectives": ["1 to 5 concise objectives"],
  "style_notes": "visual style in one or two sentences",
  "scenes": [
    {{ "key": "Scene1_HookEN", "title": "short scene title",
       "narration": "full spoken sentences for this scene (this is the spine)",
       "duration_seconds": <int>, "component": "<ComponentName>",
       "props": {{ ... }}, "visual_intent": "concrete visual plan (required for Custom)" }}
  ]
}}

Components and their props:
{_PALETTE_LINE}

Rules:
- The narration is the spine; each scene's visual MUST match what is spoken at that moment.
- Open with a TitleScene and end with a BulletScene recap.
- Scene keys are ordered Scene1_..., Scene2_..., each ending in EN (e.g. Scene3_LimitEN).
- Choose the component that fits the sentence: equations->FormulaScene, a function/data->PlotScene,
  code->CodeScene, relationships/systems->DiagramScene, lists/definitions->BulletScene,
  two things contrasted->ComparisonScene, stacked layers (app/kernel/hardware)->LayeredSystemScene,
  an ordered process/lifecycle->TimelineScene, a shell command + output->TerminalScene,
  memory/page-tables/registers->MemoryScene, data moving through stages->FlowScene,
  quantities/benchmarks->BarChartScene, one headline metric->CounterScene.
- Prefer this richer palette over plain BulletScene whenever a sentence has structure (a contrast,
  layers, ordered steps, or a command) — a varied, topic-specific visual reads far better than lists.
- Use Custom rarely, only when nothing in the palette fits.
Palette hints: user=#3A86FF, gold=#FFBE0B, success=#06D6A0, purple=#9B5DE5, danger=#FB5607."""


# --------------------------------------------------------------------------- #
# Prop normalisation
# --------------------------------------------------------------------------- #
_SAFE_MATH = {
    name: getattr(math, name)
    for name in ("sin", "cos", "tan", "exp", "log", "sqrt", "pi", "e", "pow", "fabs", "atan", "asin", "acos", "sinh", "cosh", "tanh")
}
_SAFE_MATH["abs"] = abs


def _to_float(value: Any, default: float) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def sample_expr(expr: str, x0: float, x1: float, n: int = 48) -> list[list[float]]:
    """Evaluate a single-variable python expression on a grid (sandboxed math)."""
    points: list[list[float]] = []
    for i in range(n + 1):
        x = x0 + (x1 - x0) * i / n
        try:
            y = float(eval(expr, {"__builtins__": {}}, {**_SAFE_MATH, "x": x}))  # noqa: S307 (sandboxed)
            if not math.isfinite(y):
                y = 0.0
        except Exception:
            y = 0.0
        points.append([round(x, 4), round(y, 4)])
    return points


def _clamp_range(value: Any, lo: float, hi: float, fallback: tuple[float, float]) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return list(fallback)
    a = max(lo, min(hi, _to_float(value[0], fallback[0])))
    b = max(lo, min(hi, _to_float(value[1], fallback[1])))
    if b <= a:
        return list(fallback)
    return [round(a, 3), round(b, 3)]


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item).strip()]
    return []


def _bullets_from_narration(text: str, count: int = 3) -> list[str]:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    bullets = [s[:70].rstrip(" .,:;") for s in sentences[:count]]
    return bullets or ["Key idea"]


def _label_items(value: Any, fallback_label: str, narration: str) -> dict[str, Any]:
    """Coerce a comparison column into {label, items[<=5]}, tolerating LLM variants."""
    if isinstance(value, dict):
        label = (str(value.get("label") or value.get("title") or fallback_label).strip() or fallback_label)[:40]
        items = _as_str_list(value.get("items") or value.get("bullets") or value.get("points"))[:5]
    elif isinstance(value, (list, tuple)):
        label, items = fallback_label, _as_str_list(value)[:5]
    else:
        label, items = fallback_label, []
    return {"label": label, "items": items or _bullets_from_narration(narration, 3)}


def _norm_cells(value: Any) -> list[dict[str, Any]]:
    """Coerce MemoryScene cells into {label?, sub?, color?, highlight?}."""
    out: list[dict[str, Any]] = []
    if isinstance(value, (list, tuple)):
        for item in list(value)[:12]:
            if isinstance(item, dict):
                cell: dict[str, Any] = {}
                if item.get("label") is not None:
                    cell["label"] = str(item["label"])[:14]
                if item.get("sub"):
                    cell["sub"] = str(item["sub"])[:18]
                if isinstance(item.get("color"), str):
                    cell["color"] = item["color"]
                if item.get("highlight"):
                    cell["highlight"] = True
                out.append(cell or {"label": ""})
            elif isinstance(item, (str, int, float)):
                out.append({"label": str(item)[:14]})
    return out


def _norm_bars(value: Any) -> list[dict[str, Any]]:
    """Coerce BarChartScene bars into {label, value, color?}."""
    out: list[dict[str, Any]] = []
    if isinstance(value, (list, tuple)):
        for item in list(value)[:6]:
            if isinstance(item, dict):
                bar: dict[str, Any] = {
                    "label": (str(item.get("label") or item.get("name") or "?").strip() or "?")[:16],
                    "value": _to_float(item.get("value"), 0.0),
                }
                if isinstance(item.get("color"), str):
                    bar["color"] = item["color"]
                out.append(bar)
    return out


def _norm_records(value: Any, keys: tuple[str, ...], extra: tuple[str, ...], cap: int = 40) -> list[dict[str, Any]]:
    """Coerce a list of {label, ...} records (for layers/steps); skip empties."""
    out: list[dict[str, Any]] = []
    if isinstance(value, (list, tuple)):
        for item in list(value)[:5]:
            if isinstance(item, dict):
                label = ""
                for k in keys:
                    if item.get(k):
                        label = str(item[k]).strip()[:cap]
                        break
                if not label:
                    continue
                record: dict[str, Any] = {"label": label}
                for k in extra:
                    if k == "color":
                        if isinstance(item.get("color"), str):
                            record["color"] = item["color"]
                    elif item.get(k):
                        record[k] = str(item[k]).strip()[:48]
                out.append(record)
            elif isinstance(item, str) and item.strip():
                out.append({"label": item.strip()[:cap]})
    return out


def _normalise_props(scene: dict[str, Any]) -> dict[str, Any]:
    component = scene.get("component")
    props = dict(scene.get("props") or {})
    title = scene.get("title") or props.get("title") or ""
    narration = scene.get("narration") or ""
    props.setdefault("title", title)

    if component == "PlotScene":
        x_range = _clamp_range(props.get("xRange"), -50, 50, (-4.0, 4.0))
        y_range = _clamp_range(props.get("yRange"), -200, 200, (-2.0, 6.0))
        props["xRange"] = x_range
        props["yRange"] = y_range
        if not props.get("points"):
            expr = str(props.pop("expr", "") or "0.18*x**2")
            props["points"] = sample_expr(expr, x_range[0], x_range[1])
        else:
            props.pop("expr", None)
    elif component == "BulletScene":
        bullets = _as_str_list(props.get("bullets"))[:5]
        props["bullets"] = bullets or _bullets_from_narration(narration)
    elif component == "FormulaScene":
        formulas = _as_str_list(props.get("formulas"))[:3]
        props["formulas"] = formulas or ["y = f(x)"]
    elif component == "CodeScene":
        props.setdefault("code", "# code")
        props.setdefault("lang", "python")
    elif component == "DiagramScene":
        nodes = props.get("nodes") if isinstance(props.get("nodes"), list) else []
        for node in nodes:
            if isinstance(node, dict):
                node["x"] = max(-6.0, min(6.0, _to_float(node.get("x"), 0.0)))
                node["y"] = max(-3.0, min(3.0, _to_float(node.get("y"), 0.0)))
        props["nodes"] = nodes
        props["edges"] = props.get("edges") if isinstance(props.get("edges"), list) else []
    elif component == "ComparisonScene":
        props["left"] = _label_items(props.get("left"), "A", narration)
        props["right"] = _label_items(props.get("right"), "B", narration)
    elif component == "LayeredSystemScene":
        layers = _norm_records(props.get("layers"), ("label", "name", "title"), ("sub", "color"))
        props["layers"] = layers or [{"label": b} for b in _bullets_from_narration(narration, 4)]
    elif component == "TimelineScene":
        steps = _norm_records(props.get("steps"), ("label", "name", "title"), ("sub",), cap=36)
        props["steps"] = steps or [{"label": b} for b in _bullets_from_narration(narration, 4)]
    elif component == "TerminalScene":
        props["command"] = str(props.get("command") or props.get("cmd") or "echo hello").strip()[:120]
        output = props.get("output")
        if output is not None:
            props["output"] = str(output)[:500]
    elif component == "MemoryScene":
        cells = _norm_cells(props.get("cells"))
        props["cells"] = cells or [{"label": f"0x{i:X}"} for i in range(8)]
        props["cols"] = max(1, min(6, int(_to_float(props.get("cols"), 4))))
    elif component == "FlowScene":
        stages = _norm_records(props.get("stages"), ("label", "name", "title"), ("sub",), cap=24)
        props["stages"] = stages or [{"label": b} for b in _bullets_from_narration(narration, 4)]
    elif component == "BarChartScene":
        bars = _norm_bars(props.get("bars"))
        if not bars:
            sentences = _bullets_from_narration(narration, 4)
            bars = [
                {"label": (s.split()[0] if s.split() else "?")[:12], "value": float((i + 2) * 2)}
                for i, s in enumerate(sentences)
            ]
        props["bars"] = bars
    elif component == "CounterScene":
        props["value"] = _to_float(props.get("value"), 100.0)
        for key in ("prefix", "suffix", "label"):
            if props.get(key) is not None:
                props[key] = str(props[key])[:40]
        if props.get("decimals") is not None:
            props["decimals"] = max(0, min(3, int(_to_float(props.get("decimals"), 0))))
    return props


def _normalise_component(value: Any) -> str:
    raw = str(value or "").strip()
    if raw in _ALLOWED_COMPONENTS:
        return raw
    return _COMPONENT_ALIASES.get(raw.lower().replace(" ", "_"), "BulletScene")


def _normalise_key(value: Any, index: int) -> str:
    raw = str(value or "").strip()
    match = re.match(r"^Scene(\d+)_([A-Za-z0-9]+?)(?:EN)?$", raw)
    if match:
        return f"Scene{index}_{match.group(2)}EN"
    cleaned = re.sub(r"[^A-Za-z0-9]+", "", raw) or "Scene"
    return f"Scene{index}_{cleaned}EN"


def normalize_remotion_blueprint(data: Any, target_duration_seconds: int) -> dict[str, Any]:
    """Coerce common LLM output variants into a RemotionBlueprint-shaped dict."""
    if not isinstance(data, dict):
        raise ValueError("Remotion blueprint must be a JSON object")
    coerced = dict(data)
    coerced.setdefault("target_duration_seconds", target_duration_seconds)
    subject = str(coerced.get("subject_area") or coerced.get("theme") or "general_stem").strip().lower().replace("-", "_")
    coerced["subject_area"] = subject if subject in {
        "math", "physics", "cs", "biology", "chemistry", "engineering", "general_stem"
    } else "general_stem"
    difficulty = str(coerced.get("difficulty") or "intro").strip().lower()
    coerced["difficulty"] = difficulty if difficulty in {"intro", "intermediate", "advanced"} else "intro"
    coerced["learning_objectives"] = (
        coerced.get("learning_objectives") or coerced.get("objectives") or ["Explain the core idea clearly."]
    )
    if not coerced.get("slug"):
        base = str(coerced.get("title") or "remotion-video")
        coerced["slug"] = (re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-") or "remotion-video")[:60]
    coerced.setdefault("theme", "general-stem")

    raw_scenes = coerced.get("scenes")
    if not isinstance(raw_scenes, list) or not raw_scenes:
        raise ValueError("Remotion blueprint produced no scenes")
    scenes: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_scenes, start=1):
        if not isinstance(raw, dict):
            continue
        scene = dict(raw)
        scene["key"] = _normalise_key(scene.get("key"), index)
        scene["title"] = scene.get("title") or scene.get("name") or f"Scene {index}"
        scene["narration"] = (
            scene.get("narration")
            or scene.get("text")
            or scene.get("voiceover")
            or scene.get("script")
            or scene.get("spoken_text")
            or ""
        )
        scene["component"] = _normalise_component(scene.get("component"))
        scene["visual_intent"] = scene.get("visual_intent") or scene.get("visual") or scene.get("visual_description") or ""
        scene["props"] = _normalise_props(scene)
        scene.pop("name", None)
        scene.pop("text", None)
        scenes.append(scene)
    coerced["scenes"] = scenes
    return coerced


# --------------------------------------------------------------------------- #
# Deterministic fake blueprint (FAKE_LLM / tests / docker smoke)
# --------------------------------------------------------------------------- #
def _component_for_layout(layout: str, is_first: bool, is_last: bool) -> str:
    if is_first:
        return "TitleScene"
    if is_last:
        return "BulletScene"
    return {
        "graph_plot": "PlotScene",
        "equation_transform": "FormulaScene",
        "spatial_model": "DiagramScene",
        "process_flow": "DiagramScene",
    }.get(layout, "BulletScene")


def _props_for(component: str, title: str, narration: str, beats: list[Any]) -> dict[str, Any]:
    labels = [getattr(b, "label", "") or getattr(b, "text_hint", "") for b in beats]
    labels = [lbl[:60] for lbl in labels if lbl][:4] or _bullets_from_narration(narration)
    if component == "TitleScene":
        return {"title": title, "subtitle": "A visual, step-by-step explanation", "accent": "#9B5DE5"}
    if component == "PlotScene":
        return {
            "title": title,
            "points": sample_expr("0.18*x**2", -4.0, 4.0),
            "xRange": [-4, 4],
            "yRange": [-1, 5],
            "sweep": True,
            "xLabel": "x",
            "yLabel": "y",
            "caption": "How the quantity changes",
        }
    if component == "FormulaScene":
        return {
            "title": title,
            "formulas": ["f'(x) = \\lim_{h \\to 0} \\frac{f(x+h)-f(x)}{h}"],
            "caption": "The limit definition",
        }
    if component == "DiagramScene":
        return {
            "title": title,
            "nodes": [
                {"id": "a", "label": "Input", "x": -3.2, "y": 0, "color": "#3A86FF"},
                {"id": "b", "label": "Process", "x": 0, "y": 0, "color": "#9B5DE5"},
                {"id": "c", "label": "Output", "x": 3.2, "y": 0, "color": "#06D6A0"},
            ],
            "edges": [
                {"from": "a", "to": "b", "label": ""},
                {"from": "b", "to": "c", "label": ""},
            ],
            "caption": "How the pieces connect",
        }
    return {"title": title, "bullets": labels, "caption": ""}


def fake_remotion_blueprint(
    prompt: str,
    theme: str | None = None,
    target_duration_seconds: int | None = None,
) -> RemotionBlueprint:
    """Build a deterministic, gate-passing Remotion blueprint.

    Reuses the curated academic narration from the Manim ``fake_blueprint`` (so
    the narration always clears the shared duration gate) and assigns each scene
    a palette component based on its layout.
    """
    from video_api.pipeline.llm import fake_blueprint  # deferred: avoid import cycle

    base = fake_blueprint(prompt, theme, target_duration_seconds)
    scenes: list[dict[str, Any]] = []
    last_index = len(base.scenes) - 1
    for index, scene in enumerate(base.scenes):
        component = _component_for_layout(scene.layout, index == 0, index == last_index)
        scenes.append(
            {
                "key": scene.key,
                "title": scene.title,
                "narration": scene.text,
                "duration_seconds": scene.duration_seconds,
                "component": component,
                "props": _props_for(component, scene.title, scene.text, scene.beats),
                "visual_intent": scene.visual_intent,
            }
        )
    return RemotionBlueprint(
        title=base.title,
        theme=base.theme,
        slug=base.slug,
        target_duration_seconds=base.target_duration_seconds,
        subject_area=base.subject_area,
        difficulty=base.difficulty,
        audience=base.audience,
        teaching_goal=base.teaching_goal,
        learning_objectives=base.learning_objectives,
        style_notes=base.style_notes,
        scenes=scenes,
    )
