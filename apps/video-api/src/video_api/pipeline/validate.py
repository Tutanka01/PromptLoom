from __future__ import annotations

import ast
import builtins
import json
import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path

from video_api.schemas import CLASS_KEY_RE


logger = logging.getLogger(__name__)


_FORBIDDEN_CALLS = frozenset({"eval", "exec", "__import__", "compile", "open", "breakpoint", "input"})
_FORBIDDEN_ATTRS = frozenset({"system", "popen", "run", "call", "Popen", "check_output", "check_call"})
_FORBIDDEN_MODULES = frozenset({"os", "sys", "subprocess", "socket", "urllib", "requests", "httpx", "importlib", "ctypes", "shutil", "pickle", "shelve"})
_TEX_CALLS = frozenset({"Tex", "MathTex"})


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _literal_strings(node: ast.Call) -> list[str]:
    strings = []
    for arg in node.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            strings.append(arg.value)
    for keyword in node.keywords:
        if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
            strings.append(keyword.value.value)
    return strings


def validate_scene_ast_security(source: str, scene_key: str) -> None:
    """Raise ValueError if generated scene code contains unsafe patterns.

    Checks: forbidden function calls (eval/exec/open), forbidden module attributes
    (os.system, subprocess.run), and unexpected import statements.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError(f"Syntax error in generated scene {scene_key}: {exc}") from exc

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            else:
                names = [(node.module or "").split(".")[0]]
            for name in names:
                if name in _FORBIDDEN_MODULES:
                    raise ValueError(
                        f"Forbidden import '{name}' in generated scene {scene_key}"
                    )
                if name and name not in {"manim", "numpy", "json", "pathlib", "math", "collections", "itertools", "functools", ""}:
                    raise ValueError(
                        f"Unexpected import '{name}' in generated scene {scene_key} — helpers are already imported"
                    )
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_CALLS:
                raise ValueError(
                    f"Forbidden call '{node.func.id}()' in generated scene {scene_key}"
                )
            if isinstance(node.func, ast.Attribute) and node.func.attr in _FORBIDDEN_ATTRS:
                raise ValueError(
                    f"Forbidden attribute call '.{node.func.attr}()' in generated scene {scene_key}"
                )
            call_name = _call_name(node.func)
            if call_name in _TEX_CALLS:
                for value in _literal_strings(node):
                    if not value.isascii():
                        raise ValueError(
                            f"{call_name}() in generated scene {scene_key} contains non-ASCII text; "
                            "use Text()/t()/mono() for labels, words, icons, and Unicode, "
                            "and reserve Tex/MathTex for ASCII LaTeX math."
                        )


APPROVED_VISUAL_PRIMITIVES = {
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
}


def validate_static_video_source(video_dir: Path) -> None:
    logger.info("validate.start video_dir=%s", video_dir)
    segments_path = video_dir / "segments_en.json"
    beats_path = video_dir / "beats_en.json"
    if not segments_path.exists():
        raise ValueError("segments_en.json missing")
    if not beats_path.exists():
        raise ValueError("beats_en.json missing")

    segments = json.loads(segments_path.read_text(encoding="utf-8"))["segments"]
    beats = json.loads(beats_path.read_text(encoding="utf-8"))
    keys = [segment["key"] for segment in segments]
    logger.info("validate.segments video_dir=%s segments=%d beat_sets=%d", video_dir, len(segments), len(beats))
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate segment keys")
    for segment in segments:
        if segment["key"] != segment["class"]:
            raise ValueError(f"segment key/class mismatch: {segment['key']}")
        if len(str(segment.get("text", "")).split()) < 10:
            raise ValueError(f"segment narration too short: {segment['key']}")
        if not CLASS_KEY_RE.match(segment["key"]):
            raise ValueError(f"invalid segment key: {segment['key']}")
        if segment["key"] not in beats:
            raise ValueError(f"missing beats for {segment['key']}")
        scene_beats = beats[segment["key"]]
        if len(scene_beats) < 3:
            raise ValueError(f"too few beats for {segment['key']}")
        ats = [float(beat["at"]) for beat in scene_beats]
        if ats != sorted(ats):
            raise ValueError(f"beats are not sorted for {segment['key']}")
        if ats[-1] < 0.75:
            raise ValueError(f"last beat too early for {segment['key']}")
        for beat in scene_beats:
            action = str(beat.get("visual_action", "")).strip().lower()
            if action in {"make it nice", "show something", "more explanation", "animate"}:
                raise ValueError(f"vague visual action for {segment['key']}: {action}")

    transition_sfx = video_dir / "build_transition_sfx.py"
    if not transition_sfx.exists():
        raise ValueError("build_transition_sfx.py missing")
    py_files = (
        list(video_dir.glob("*_en.py"))
        + list(video_dir.glob("*_style.py"))
        + [video_dir / "generate_voice_en.py", transition_sfx]
    )
    manim_files = [path for path in video_dir.glob("*_en.py") if path.name != "generate_voice_en.py"]
    # Scenes are now authored as free-form Manim (scene_coder); the `layout_name`
    # attribute only appears on scenes that fell back to the deterministic template.
    # We still reject an unknown primitive on those fallback scenes as a safety check,
    # but we no longer enforce "visual variety" here — variety is the job of the
    # generated scenes, and penalising a job because its safety-net fallbacks share a
    # layout would reject otherwise valid output.
    for manim_path in manim_files:
        source = manim_path.read_text(encoding="utf-8")
        layouts = re.findall(r'layout_name = "([a-z_]+)"', source)
        unknown = sorted(set(layouts) - APPROVED_VISUAL_PRIMITIVES)
        if unknown:
            raise ValueError(f"generated scenes use unknown visual primitives: {unknown}")

    for path in py_files:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    subprocess.run(
        ["python3", "-m", "py_compile", *[str(path) for path in py_files]],
        check=True,
        cwd=video_dir,
        capture_output=True,
        text=True,
    )
    logger.info("validate.done video_dir=%s python_files=%d", video_dir, len(py_files))


# ---------------------------------------------------------------------------
# Per-scene runtime validation
#
# Syntax + security checks let a syntactically-valid but undefined symbol (e.g.
# a hallucinated `GlowDots(...)`) slip through to the global render, where it
# raises NameError and kills the whole job instead of falling back to the
# deterministic template for that one scene. These two checks catch such errors
# at the per-scene stage so the scene-coder repair loop (and ultimately the
# fallback template) can do its job and a video still ships.
# ---------------------------------------------------------------------------

_BUILTIN_NAMES = frozenset(dir(builtins))

_manim_namespace_cache: set[str] | None = None
_manim_namespace_checked = False


def manim_namespace() -> set[str] | None:
    """Return the names exported by the installed manim package, or None if manim
    cannot be imported in this environment (dev/test boxes without manim)."""
    global _manim_namespace_cache, _manim_namespace_checked
    if not _manim_namespace_checked:
        _manim_namespace_checked = True
        try:
            import manim  # type: ignore

            _manim_namespace_cache = set(dir(manim))
        except Exception:  # pragma: no cover - depends on environment
            _manim_namespace_cache = None
    return _manim_namespace_cache


def _has_star_import(tree: ast.AST) -> bool:
    return any(
        isinstance(node, ast.ImportFrom)
        and any(alias.name == "*" for alias in node.names)
        for node in ast.walk(tree)
    )


def _collect_bound_names(tree: ast.AST) -> set[str]:
    """Over-approximate every name bound anywhere in the module.

    Over-approximation is the safe direction: it only ever allows *more* names,
    so it cannot turn valid code into a false positive.
    """
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bound.add(node.id)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                bound.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    bound.add(alias.asname or alias.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            bound.update(node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
    return bound


def validate_scene_names(module_source: str, scene_key: str) -> None:
    """Raise ValueError if the module references a name that is not a manim symbol,
    a documented helper/import, a local binding, or a builtin.

    Catches the most common scene-coder hallucination — inventing a Manim class or
    helper that does not exist (`GlowDots`, `FlashArrow`, ...). No-op when manim is
    not importable and the module relies on `from manim import *`, to avoid false
    positives in environments where the manim namespace is unknown.
    """
    try:
        tree = ast.parse(module_source)
    except SyntaxError:
        return  # syntax errors are reported by ast.parse() in the caller

    manim_ns = manim_namespace()
    if _has_star_import(tree) and manim_ns is None:
        return

    allowed = set(_BUILTIN_NAMES) | _collect_bound_names(tree)
    if manim_ns:
        allowed |= manim_ns

    undefined: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id not in allowed:
                undefined.append(node.id)

    if undefined:
        uniq = list(dict.fromkeys(undefined))
        raise ValueError(
            f"Scene {scene_key} references undefined name(s): {', '.join(uniq[:5])}. "
            "These are not Manim Community symbols, documented helpers, imports, or "
            "local variables. Use only real Manim classes and the documented helpers."
        )


def _error_tail(text: str, max_lines: int = 25) -> str:
    lines = [line for line in (text or "").splitlines() if line.strip()]
    return "\n".join(lines[-max_lines:])


def smoke_render_scene(
    video_dir: Path,
    scene_key: str,
    module_source: str,
    timeout_seconds: int,
) -> None:
    """Render a single scene's last frame to prove its construct() actually executes.

    Raises ValueError (with the error tail) if the scene fails to render. No-op when
    manim is not importable in this environment, so dev/test boxes are unaffected.
    """
    if manim_namespace() is None:
        logger.info("smoke_render.skip scene=%s reason=manim_unavailable", scene_key)
        return

    smoke_path = video_dir / f"_smoke_{scene_key}.py"
    smoke_path.write_text(module_source, encoding="utf-8")
    cmd = [sys.executable, "-m", "manim", "-ql", "-s", smoke_path.name, scene_key]
    logger.info("smoke_render.start scene=%s file=%s", scene_key, smoke_path.name)
    try:
        proc = subprocess.run(
            cmd,
            cwd=video_dir,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError(
            f"Scene {scene_key} smoke render timed out after {timeout_seconds}s"
        ) from exc
    finally:
        smoke_path.unlink(missing_ok=True)
        for artifact_root in ("videos", "images"):
            artifact_dir = video_dir / "media" / artifact_root / smoke_path.stem
            if artifact_dir.exists():
                shutil.rmtree(artifact_dir, ignore_errors=True)

    if proc.returncode != 0:
        tail = _error_tail(proc.stderr) or _error_tail(proc.stdout)
        logger.warning("smoke_render.failed scene=%s rc=%d", scene_key, proc.returncode)
        raise ValueError(f"Scene {scene_key} failed to render:\n{tail}")
    logger.info("smoke_render.ok scene=%s", scene_key)
