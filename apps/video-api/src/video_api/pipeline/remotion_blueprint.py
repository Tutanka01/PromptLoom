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

from video_api.schemas import REMOTION_PALETTE, RemotionBlueprint

logger = logging.getLogger(__name__)


_ALLOWED_COMPONENTS = set(REMOTION_PALETTE) | {"Custom"}

# Mirrors TRANSITIONS in remotion/src/MainComposition.tsx (+ "auto").
_TRANSITIONS = {"auto", "fade", "rise", "slide-left", "scale", "slide-right", "wipe"}

# Mirrors ICON_NAMES in remotion/src/catalog/Icon.tsx (parity covered by a test).
ICON_NAMES = frozenset({
    "activity", "alert", "arrow-right", "atom", "beaker", "binary", "book", "box",
    "braces", "brain", "bug", "cable", "calculator", "chart", "circuit", "clock",
    "cloud", "code", "cog", "compass", "cpu", "database", "disc", "dna", "exchange",
    "file", "filter", "flask", "folder", "function", "gauge", "git", "globe",
    "graduation", "hash", "infinity", "key", "layers", "lightbulb", "lock", "magnet",
    "memory", "microscope", "monitor", "network", "orbit", "package", "pi", "pointer",
    "radio", "refresh", "repeat", "rocket", "ruler", "scale", "search", "server",
    "settings", "shield", "shuffle", "sigma", "smartphone", "sparkles", "storage",
    "table", "target", "telescope", "terminal", "test-tube", "thermometer", "timer",
    "trending", "triangle", "unlock", "usb", "variable", "waves", "wifi", "workflow",
    "wrench", "x", "zap",
})


def _norm_icon(value: Any) -> str | None:
    """Validate an icon name against the allow-list; unknown -> None (dropped)."""
    name = str(value or "").strip().lower()
    if not name:
        return None
    if name in ICON_NAMES:
        return name
    logger.info("remotion_blueprint.icon_dropped name=%s", name)
    return None

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
    "image": "ImageScene",
    "imagescene": "ImageScene",
    "photo": "ImageScene",
    "still": "ImageScene",
    "footage": "FootageScene",
    "footagescene": "FootageScene",
    "video": "FootageScene",
    "broll": "FootageScene",
    "b_roll": "FootageScene",
    "custom": "Custom",
    "freeform": "Custom",
    "free": "Custom",
}

_PALETTE_LINE = (
    "- TitleScene:   { title: str, subtitle?: str, accent?: \"#hex\" }  — open a video/section\n"
    "- BulletScene:  { title: str, bullets: [str, ...(2-5)], icons?: [icon_name|null per bullet], caption?: str, accent?: \"#hex\" }\n"
    "- FormulaScene: { title: str, formulas: [latex_str, ...(1-3)], caption?: str }\n"
    "      latex example: \"f'(x) = \\\\lim_{h \\\\to 0} \\\\frac{f(x+h)-f(x)}{h}\" (escape backslashes for JSON)\n"
    "- CodeScene:    { title: str, code: \"line1\\nline2\", lang: \"python|c|bash|tsx\", codeTitle?: str, caption?: str }\n"
    "- PlotScene:    { title: str, expr: \"python expr in x, e.g. 0.18*x**2 or sin(x)\",\n"
    "                  xRange: [min,max], yRange: [min,max], sweep?: bool, area?: bool, xLabel?: str, yLabel?: str, caption?: str }\n"
    "- DiagramScene: { title: str,\n"
    "                  nodes: [ {id: str, label: str, x: number(-6..6), y: number(-3..3), color?: \"#hex\", icon?: icon_name} ],\n"
    "                  edges: [ {from: id, to: id, color?: \"#hex\", label?: str} ], caption?: str }\n"
    "- ComparisonScene: { title: str, left: {label: str, items: [str, ...(2-5)]},\n"
    "                  right: {label: str, items: [str, ...(2-5)]}, caption?: str }  — two columns side by side (user vs kernel, before vs after)\n"
    "- LayeredSystemScene: { title: str, layers: [ {label: str, sub?: str, color?: \"#hex\"}, ...(2-5) ], caption?: str }  — stacked bands top->bottom (e.g. App / System Call / Kernel / Hardware)\n"
    "- TimelineScene: { title: str, steps: [ {label: str, sub?: str}, ...(2-5) ], caption?: str }  — left->right sequence / process / lifecycle\n"
    "- TerminalScene: { title: str, command: str, output?: str, caption?: str }  — a shell command typed out + its output\n"
    "- MemoryScene:  { title: str, cells: [ {label?: str, sub?: str, color?: \"#hex\", highlight?: bool}, ...(up to 12) ], cols?: int(1-6), caption?: str }  — grid of cells: memory, page tables, registers, stack frames\n"
    "- FlowScene:    { title: str, stages: [ {label: str, sub?: str, icon?: icon_name}, ...(2-5) ], caption?: str }  — a packet travels left->right through stages (data flow, a syscall's path)\n"
    "- BarChartScene: { title: str, bars: [ {label: str, value: number, color?: \"#hex\"}, ...(2-6) ], caption?: str }  — quantities / benchmarks / comparisons\n"
    "- CounterScene: { title: str, value: number, prefix?: str, suffix?: str, label?: str, decimals?: int, caption?: str }  — one big animated metric (throughput, size, count)\n"
    "- ImageScene:   { title: str, asset_query: str, caption?: str, motion?: \"ken-burns|pan-left|pan-right|push-in\" } — a sourced still image; NEVER provide a URL\n"
    "- FootageScene: { title: str, asset_query: str, caption?: str, motion?: \"push-in|static\" } — sourced real B-roll; NEVER provide a URL\n"
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
       "props": {{ ... }},
       "source_ids": ["src_01"],
       "beats": [ {{ "anchor": "3-8 word phrase copied VERBATIM from this scene's narration" }} ],
       "visual_intent": "concrete visual plan (required for Custom)" }}
  ]
}}

Components and their props:
{_PALETTE_LINE}

Rules:
- The narration is the spine; each scene's visual MUST match what is spoken at that moment.
- Open with a visually active hook and end with a concise BulletScene recap. A short TitleScene is
  allowed, but a ComparisonScene, exact ImageScene/FootageScene, or Custom hook is often stronger.
- Scene keys are ordered Scene1_..., Scene2_..., each ending in EN (e.g. Scene3_LimitEN).
- Choose the component that fits the sentence: equations->FormulaScene, a function/data->PlotScene,
  code->CodeScene, relationships/systems->DiagramScene, lists/definitions->BulletScene,
  two things contrasted->ComparisonScene, stacked layers (app/kernel/hardware)->LayeredSystemScene,
  an ordered process/lifecycle->TimelineScene, a shell command + output->TerminalScene,
  memory/page-tables/registers->MemoryScene, data moving through stages->FlowScene,
  quantities/benchmarks->BarChartScene, one headline metric->CounterScene.
- Prefer this richer palette over plain BulletScene whenever a sentence has structure (a contrast,
  layers, ordered steps, or a command) — a varied, topic-specific visual reads far better than lists.
- BEATS: for every scene whose component shows multiple items (bullets, layers, steps, stages, cells,
  nodes, formulas, comparison items), add "beats": one anchor per visual item, in display order.
  Each anchor is the exact 3-8 word phrase from THIS scene's narration spoken at the moment that item
  should appear (copy it verbatim, do not paraphrase). The renderer aligns the voiceover and reveals
  each item exactly when its anchor is spoken. For ComparisonScene, order anchors as all left items
  then all right items. Scenes with a single visual (TitleScene, CounterScene) may omit beats.
- Use Custom rarely, only when nothing in the palette fits.
- Use ImageScene/FootageScene only when production_context.visuals.allow_stock is true and a real-world
  image adds meaning. Never use generic server-room B-roll while explaining an invisible mechanism.
- CINEMATIC MODE: build a motion-led sequence, not a slide deck. Keep BulletScene for the final recap
  only whenever the material can be visualised structurally. Prefer FlowScene, DiagramScene,
  TimelineScene, PlotScene, MemoryScene, ComparisonScene, or a justified Custom scene. If stock media
  is allowed and the topic has an observable real-world anchor, include 1-2 semantically exact media
  scenes with precise asset_query values. The narration of a media scene must explicitly discuss what
  the image proves or grounds. Do not add decorative media just to satisfy a quota.
- When research_context is present, attach only its valid IDs as scene.source_ids. Never invent IDs.
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


def _norm_beats(value: Any) -> list[dict[str, str]]:
    """Coerce blueprint beats into [{anchor}], tolerating strings and aliases.

    Anchors are matched fuzzily against the aligned audio downstream
    (pipeline/beats.py); an anchor the TTS never speaks simply resolves to a
    null cue, so light coercion here is safe.
    """
    out: list[dict[str, str]] = []
    if isinstance(value, (list, tuple)):
        for item in list(value)[:10]:
            if isinstance(item, str):
                anchor = item
            elif isinstance(item, dict):
                anchor = str(
                    item.get("anchor") or item.get("phrase") or item.get("text") or item.get("when") or ""
                )
            else:
                continue
            anchor = " ".join(anchor.split())[:80]
            if len(anchor) >= 3:
                out.append({"anchor": anchor})
    return out


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
                    elif k == "icon":
                        icon = _norm_icon(item.get("icon"))
                        if icon:
                            record["icon"] = icon
                    elif item.get(k):
                        record[k] = str(item[k]).strip()[:48]
                out.append(record)
            elif isinstance(item, str) and item.strip():
                out.append({"label": item.strip()[:cap]})
    return out


def _normalise_props(scene: dict[str, Any], degradations: list[str] | None = None) -> dict[str, Any]:
    component = scene.get("component")
    props = dict(scene.get("props") or {})
    title = scene.get("title") or props.get("title") or ""
    narration = scene.get("narration") or ""
    props.setdefault("title", title)

    def degrade(message: str) -> None:
        # A placeholder keeps the render alive, but it is content the viewer was
        # never meant to see — record it so report.json can expose it.
        full = f"{scene.get('key', '?')}: {message}"
        logger.warning("remotion_blueprint.degraded %s", full)
        if degradations is not None:
            degradations.append(full)

    if component == "PlotScene":
        x_range = _clamp_range(props.get("xRange"), -50, 50, (-4.0, 4.0))
        y_range = _clamp_range(props.get("yRange"), -200, 200, (-2.0, 6.0))
        props["xRange"] = x_range
        props["yRange"] = y_range
        if not props.get("points"):
            expr = str(props.pop("expr", "") or "")
            if not expr:
                degrade("PlotScene without expr/points — generic parabola injected")
                expr = "0.18*x**2"
            props["points"] = sample_expr(expr, x_range[0], x_range[1])
        else:
            props.pop("expr", None)
    elif component == "BulletScene":
        bullets = _as_str_list(props.get("bullets"))[:5]
        if not bullets:
            degrade("BulletScene without bullets — derived from narration sentences")
            bullets = _bullets_from_narration(narration)
        props["bullets"] = bullets
        if props.get("icons") is not None:
            raw_icons = props["icons"] if isinstance(props["icons"], (list, tuple)) else []
            props["icons"] = [_norm_icon(icon) for icon in list(raw_icons)[: len(bullets)]]
    elif component == "FormulaScene":
        formulas = _as_str_list(props.get("formulas"))[:3]
        if not formulas:
            degrade("FormulaScene without formulas — placeholder 'y = f(x)' injected")
            formulas = ["y = f(x)"]
        props["formulas"] = formulas
    elif component == "CodeScene":
        if not str(props.get("code") or "").strip():
            degrade("CodeScene without code — placeholder comment injected")
            props["code"] = "# code"
        props.setdefault("lang", "python")
    elif component == "DiagramScene":
        nodes = props.get("nodes") if isinstance(props.get("nodes"), list) else []
        if not nodes:
            degrade("DiagramScene without nodes")
        for node in nodes:
            if isinstance(node, dict):
                node["x"] = max(-6.0, min(6.0, _to_float(node.get("x"), 0.0)))
                node["y"] = max(-3.0, min(3.0, _to_float(node.get("y"), 0.0)))
                icon = _norm_icon(node.get("icon"))
                if icon:
                    node["icon"] = icon
                else:
                    node.pop("icon", None)
        props["nodes"] = nodes
        props["edges"] = props.get("edges") if isinstance(props.get("edges"), list) else []
    elif component == "ComparisonScene":
        if not isinstance(props.get("left"), (dict, list)) or not isinstance(props.get("right"), (dict, list)):
            degrade("ComparisonScene missing a column — derived from narration")
        props["left"] = _label_items(props.get("left"), "A", narration)
        props["right"] = _label_items(props.get("right"), "B", narration)
    elif component == "LayeredSystemScene":
        layers = _norm_records(props.get("layers"), ("label", "name", "title"), ("sub", "color"))
        if not layers:
            degrade("LayeredSystemScene without layers — derived from narration")
            layers = [{"label": b} for b in _bullets_from_narration(narration, 4)]
        props["layers"] = layers
    elif component == "TimelineScene":
        steps = _norm_records(props.get("steps"), ("label", "name", "title"), ("sub",), cap=36)
        if not steps:
            degrade("TimelineScene without steps — derived from narration")
            steps = [{"label": b} for b in _bullets_from_narration(narration, 4)]
        props["steps"] = steps
    elif component == "TerminalScene":
        command = str(props.get("command") or props.get("cmd") or "").strip()
        if not command:
            degrade("TerminalScene without command — placeholder 'echo hello' injected")
            command = "echo hello"
        props["command"] = command[:120]
        output = props.get("output")
        if output is not None:
            props["output"] = str(output)[:500]
    elif component == "MemoryScene":
        cells = _norm_cells(props.get("cells"))
        if not cells:
            degrade("MemoryScene without cells — generic 0x0..0x7 grid injected")
            cells = [{"label": f"0x{i:X}"} for i in range(8)]
        props["cells"] = cells
        props["cols"] = max(1, min(6, int(_to_float(props.get("cols"), 4))))
    elif component == "FlowScene":
        stages = _norm_records(props.get("stages"), ("label", "name", "title"), ("sub", "icon"), cap=24)
        if not stages:
            degrade("FlowScene without stages — derived from narration")
            stages = [{"label": b} for b in _bullets_from_narration(narration, 4)]
        props["stages"] = stages
    elif component == "BarChartScene":
        bars = _norm_bars(props.get("bars"))
        if not bars:
            degrade("BarChartScene without bars — INVENTED values injected")
            sentences = _bullets_from_narration(narration, 4)
            bars = [
                {"label": (s.split()[0] if s.split() else "?")[:12], "value": float((i + 2) * 2)}
                for i, s in enumerate(sentences)
            ]
        props["bars"] = bars
    elif component == "CounterScene":
        if props.get("value") is None:
            degrade("CounterScene without value — placeholder 100 injected")
        props["value"] = _to_float(props.get("value"), 100.0)
        for key in ("prefix", "suffix", "label"):
            if props.get(key) is not None:
                props[key] = str(props[key])[:40]
        if props.get("decimals") is not None:
            props["decimals"] = max(0, min(3, int(_to_float(props.get("decimals"), 0))))
    elif component in {"ImageScene", "FootageScene"}:
        query = " ".join(str(props.get("asset_query") or props.get("query") or title).split())[:180]
        if not query:
            degrade(f"{component} without asset_query")
            query = str(title or "educational technology")
        props["asset_query"] = query
        props.pop("query", None)
        # Direct URLs from an LLM are untrusted and have unknown rights. The
        # worker's allow-listed asset provider is the only code allowed to set src.
        props.pop("src", None)
        motion = str(props.get("motion") or ("ken-burns" if component == "ImageScene" else "push-in"))
        allowed = {"ken-burns", "pan-left", "pan-right", "push-in", "static"}
        props["motion"] = motion if motion in allowed else "push-in"
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
    degradations: list[str] = list(coerced.get("degradations") or [])
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
        scene["props"] = _normalise_props(scene, degradations)
        scene["beats"] = _norm_beats(scene.get("beats") or scene.get("anchors") or scene.get("cues"))
        raw_source_ids = scene.get("source_ids") or scene.get("sources") or []
        if isinstance(raw_source_ids, str):
            raw_source_ids = [raw_source_ids]
        scene["source_ids"] = [
            str(source_id)[:40]
            for source_id in raw_source_ids
            if isinstance(source_id, (str, int)) and str(source_id).strip()
        ][:12]
        transition = str(scene.get("transition") or "auto").strip().lower()
        scene["transition"] = transition if transition in _TRANSITIONS else "auto"
        scene.pop("name", None)
        scene.pop("text", None)
        scenes.append(scene)
    coerced["scenes"] = scenes
    coerced["degradations"] = degradations
    return coerced


# --------------------------------------------------------------------------- #
# Two-pass generation: outline prompt + per-scene prompt + strict validation
# --------------------------------------------------------------------------- #

REMOTION_OUTLINE_PROMPT = f"""You are a STEM explainer-video director planning a short narrated video.
Design ONLY the pedagogical outline as STRICT JSON — scene narrations and props are written later,
one scene at a time, from your outline.

Return ONLY one JSON object (no prose, no fences):
{{
  "title": "short video title",
  "theme": "kebab-case theme",
  "slug": "kebab-case-slug",
  "subject_area": "math | physics | cs | biology | chemistry | engineering | general_stem",
  "difficulty": "intro | intermediate | advanced",
  "audience": "who this is for",
  "teaching_goal": "one sentence",
  "learning_objectives": ["1 to 5 concise objectives"],
  "style_notes": "visual style in one or two sentences",
  "scenes": [
    {{ "key": "Scene1_HookEN", "title": "short scene title",
       "component": "<ComponentName>", "duration_seconds": <int>,
       "goal": "the ONE idea this scene must make click (1-2 sentences)",
       "visual_idea": "concrete, topic-specific visual plan (1-2 sentences)",
       "source_ids": ["src_01"] }}
  ]
}}

Available components (props come later; pick by what the scene shows):
{_PALETTE_LINE}

Rules:
- Plan the explanation from intuition, to mechanism, to transfer or recap. Scene 1 is a visually
  active hook built around a question, surprising fact, exact real-world image, or concrete contrast;
  the last scene is a BulletScene recap of the key takeaways.
- A short TitleScene is allowed but not mandatory. Scene keys ordered Scene1_...EN, Scene2_...EN.
- AT MOST 2 BulletScene in the whole video (recap included). Every idea with structure gets a
  structural component: contrast->ComparisonScene, layers->LayeredSystemScene, ordered process->
  TimelineScene or FlowScene, function/data->PlotScene, equations->FormulaScene, code->CodeScene,
  command->TerminalScene, memory->MemoryScene, relationships->DiagramScene.
- Each scene teaches exactly ONE idea; goals must build on each other in order.
- If research_context is supplied, add `source_ids` to each outline scene using only IDs present there.
- Respect production_context: use ImageScene/FootageScene only when stock media is allowed and semantically exact.
- When production_context.mode is "cinematic", keep BulletScene for the final recap only whenever a
  structural visual is possible. Use a varied motion-led mix. If stock media is allowed and an
  observable real-world anchor exists, plan 1-2 precise ImageScene/FootageScene scenes whose media is
  discussed by the narration; otherwise prefer bespoke or structural motion, never generic B-roll.
- Respect the duration_policy scene count and per-scene durations handed in the user message."""

REMOTION_SCENE_PROMPT = f"""You write ONE scene of a STEM explainer video, as STRICT JSON.
You receive the video outline, this scene's goal, its component, and its neighbours for continuity.

Return ONLY one JSON object (no prose, no fences):
{{
  "narration": "full spoken sentences for this scene",
  "props": {{ ... complete props for the component ... }},
  "beats": [ {{ "anchor": "3-8 word phrase copied VERBATIM from your narration" }} ]
}}

Component prop reference:
{_PALETTE_LINE}

Rules:
- The narration is spoken aloud by a TTS voice: write natural, flowing sentences with a concrete
  example or analogy. Do not reference the screen ("as you can see"); the visual follows the words.
- Open by linking to the previous scene's idea; end by leaning toward the next scene's idea.
- Meet the word budget you are given — too few words and the scene is rejected.
- Props must be COMPLETE and topic-specific: real formulas, real code, real labels. Never leave a
  list empty, never write filler like "example" or "value".
- beats: one anchor per visual item, in display order (ComparisonScene: all left items then all
  right items). Copy each anchor verbatim from your narration — the renderer reveals the item when
  those words are spoken. Mention every visual item's content in the narration so anchors exist.
- visual term limit: ~7 words per on-screen label; put detail in the narration, not the screen.
- ICONS: where the component supports them (BulletScene icons, DiagramScene nodes[].icon,
  FlowScene stages[].icon), pick a fitting name from this list (anything else is dropped):
  {", ".join(sorted(ICON_NAMES))}
- For ImageScene/FootageScene provide a precise `asset_query`, never `src` or a URL. The worker resolves
  and licenses the media before rendering.

Example output (component=FlowScene, goal="trace the path of one read() call"):
{{
  "narration": "Let's follow a single read call from start to finish. Your program calls read, and the C library wraps that request into a system call. The CPU then switches into kernel mode, where the kernel checks that your program is allowed to touch that file. Only then does the driver pull the data off the disk and hand it back up the same path.",
  "props": {{
    "title": "The journey of read()",
    "stages": [
      {{ "label": "Program", "sub": "read()" }},
      {{ "label": "libc", "sub": "wraps the call" }},
      {{ "label": "Kernel", "sub": "checks permissions" }},
      {{ "label": "Driver", "sub": "reads the disk" }}
    ]
  }},
  "beats": [
    {{ "anchor": "Your program calls read" }},
    {{ "anchor": "the C library wraps that request" }},
    {{ "anchor": "the kernel checks that your program" }},
    {{ "anchor": "the driver pull the data" }}
  ]
}}"""

# Per-component required props for STRICT validation (pass 2). A scene that
# fails these gets a targeted retry with the error list; only after retries are
# exhausted does the lenient normalisation fill placeholders (recorded as
# degradations).
_LIST_PROPS = {
    "BulletScene": "bullets",
    "FormulaScene": "formulas",
    "LayeredSystemScene": "layers",
    "TimelineScene": "steps",
    "FlowScene": "stages",
    "DiagramScene": "nodes",
    "BarChartScene": "bars",
    "MemoryScene": "cells",
}


def _items_count(component: str, props: dict[str, Any]) -> int | None:
    """Number of cue-able visual items the component will display, or None."""
    if component in _LIST_PROPS:
        value = props.get(_LIST_PROPS[component])
        return len(value) if isinstance(value, (list, tuple)) else 0
    if component == "ComparisonScene":
        total = 0
        for side in ("left", "right"):
            value = props.get(side)
            if isinstance(value, dict) and isinstance(value.get("items"), (list, tuple)):
                total += len(value["items"][:5])
            elif isinstance(value, (list, tuple)):
                total += len(value[:5])
        return total
    if component in {"ImageScene", "FootageScene"}:
        return None
    return None


def validate_scene_payload(scene: dict[str, Any]) -> list[str]:
    """Strict per-scene checks for pass-2 output. Returns human-readable errors.

    Catches what the lenient normalisation would otherwise paper over with
    placeholders: missing/empty props, anchors that do not appear in the
    narration, and item/anchor count drift on multi-item components.
    """
    from video_api.pipeline.beats import anchor_in_text

    errors: list[str] = []
    component = str(scene.get("component") or "")
    props = scene.get("props") if isinstance(scene.get("props"), dict) else {}
    narration = str(scene.get("narration") or "")

    if len(narration.split()) < 15:
        errors.append("narration is too short — write full spoken sentences")
    if component in {"ImageScene", "FootageScene"} and not str(props.get("asset_query") or "").strip():
        errors.append(f"{component} requires a concrete props.asset_query")

    # Density: more items than the component can show kills comprehension (and
    # the renderer would silently slice them off anyway).
    item_count = _items_count(component, props)
    max_items = 12 if component == "MemoryScene" else 6
    if item_count is not None and item_count > max_items:
        errors.append(
            f"{item_count} visual items is too dense for {component} (max {max_items}) — "
            "keep the strongest items and move the rest into the narration"
        )

    if component in _LIST_PROPS:
        key = _LIST_PROPS[component]
        value = props.get(key)
        if not isinstance(value, (list, tuple)) or len([v for v in value if v]) < 2:
            errors.append(f"props.{key} must list at least 2 real items for {component}")
    elif component == "CodeScene":
        code = str(props.get("code") or "").strip()
        if len(code.splitlines()) < 2 or code in {"# code", "..."}:
            errors.append("props.code must contain real, topic-specific code (2+ lines)")
    elif component == "TerminalScene":
        command = str(props.get("command") or props.get("cmd") or "").strip()
        if not command or command == "echo hello":
            errors.append("props.command must be a real, topic-specific shell command")
    elif component == "PlotScene":
        if not props.get("expr") and not props.get("points"):
            errors.append("PlotScene needs props.expr (python expression in x) or props.points")
    elif component == "ComparisonScene":
        for side in ("left", "right"):
            value = props.get(side)
            items = value.get("items") if isinstance(value, dict) else value
            if not isinstance(items, (list, tuple)) or len(items) < 2:
                errors.append(f"props.{side}.items must list at least 2 real items")
    elif component == "CounterScene":
        if props.get("value") is None:
            errors.append("CounterScene needs a real props.value")

    beats = scene.get("beats") or []
    anchors = [
        str(b.get("anchor") if isinstance(b, dict) else b) for b in beats if b
    ]
    for anchor in anchors:
        if anchor and not anchor_in_text(narration, anchor):
            errors.append(
                f"beat anchor {anchor!r} does not appear in the narration — copy it verbatim"
            )
    expected = _items_count(component, props)
    if expected is not None and expected >= 2 and anchors:
        if abs(len(anchors) - expected) > 1:
            errors.append(
                f"{len(anchors)} beat anchors for {expected} visual items — provide one anchor "
                "per item in display order"
            )
    elif expected is not None and expected >= 2 and not anchors:
        errors.append(
            "multi-item scene without beats — add one verbatim narration anchor per visual item"
        )
    return errors


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
    if component == "FlowScene":
        return {
            "title": title,
            "stages": [
                {"label": label, "sub": f"Step {index + 1}"}
                for index, label in enumerate(labels[:4])
            ],
            "caption": "The active idea moves with the explanation",
        }
    if component == "TimelineScene":
        return {
            "title": title,
            "steps": [
                {"label": label, "sub": f"Phase {index + 1}"}
                for index, label in enumerate(labels[:4])
            ],
            "caption": "A narration-synchronised sequence",
        }
    if component == "BarChartScene":
        return {
            "title": title,
            "bars": [
                {"label": label[:24], "value": (index + 1) * 24}
                for index, label in enumerate(labels[:4])
            ],
            "caption": "A deterministic animated comparison",
        }
    if component == "LayeredSystemScene":
        return {
            "title": title,
            "layers": [
                {"label": label, "sub": f"Layer {index + 1}"}
                for index, label in enumerate(labels[:4])
            ],
            "caption": "The system is assembled layer by layer",
        }
    if component == "MemoryScene":
        return {
            "title": title,
            "cells": [
                {"label": f"0x{index * 16:02X}", "sub": label[:28], "highlight": index == 1}
                for index, label in enumerate(labels[:4])
            ],
            "cols": 4,
            "caption": "State changes remain visible and concrete",
        }
    return {"title": title, "bullets": labels, "caption": ""}


def fake_remotion_blueprint(
    prompt: str,
    theme: str | None = None,
    target_duration_seconds: int | None = None,
    production_context: dict[str, Any] | None = None,
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
    mode = str((production_context or {}).get("mode") or "technical")
    motion_first_components = [
        "TitleScene",
        "FlowScene",
        "DiagramScene",
        "PlotScene",
        "TimelineScene",
        "BarChartScene",
        "LayeredSystemScene",
        "MemoryScene",
    ]
    for index, scene in enumerate(base.scenes):
        component = (
            motion_first_components[index % len(motion_first_components)]
            if mode in {"editorial", "cinematic"}
            else _component_for_layout(scene.layout, index == 0, index == last_index)
        )
        # Verbatim leading words of each sentence double as beat anchors so the
        # fake path exercises the full align -> cues plumbing end to end.
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", scene.text) if s.strip()]
        beats = [
            {"anchor": " ".join(sentence.split()[:6])}
            for sentence in sentences[:4]
            if len(sentence.split()) >= 3
        ]
        scenes.append(
            {
                "key": scene.key,
                "title": scene.title,
                "narration": scene.text,
                "duration_seconds": scene.duration_seconds,
                "component": component,
                "props": _props_for(component, scene.title, scene.text, scene.beats),
                "beats": beats,
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
