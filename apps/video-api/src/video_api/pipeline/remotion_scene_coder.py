"""Remotion free-code escape hatch: bespoke TSX per ``Custom`` scene.

Mirrors the Manim ``SceneCoder`` (generate/repair -> validate -> smoke -> trust
or fall back). A Custom scene asks the LLM to write a self-contained React
component; it is then hard-guarded before it is trusted:

1. import allow-list  — only ``react``, ``remotion`` and the ``../../lib`` barrel;
2. forbidden-API scan — no eval/Function/fetch/require/dynamic-import/process/fs/…;
3. it must export a component named exactly after the scene key;
4. ``tsc --noEmit``    — the whole project type-checks with the candidate in place
                         (the Remotion analogue of ``validate_scene_names``);
5. smoke ``still``     — one frame of the scene actually renders.

A scene that fails every attempt is dropped to a deterministic palette
``BulletScene`` (``fallback_custom_to_palette``), so the global render always
succeeds — exactly like the Manim deterministic-template fallback.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from video_api.config import Settings

logger = logging.getLogger(__name__)

_SKILL_CACHE: str | None = None

# Module specifiers a generated scene is allowed to import from.
_ALLOWED_IMPORTS = {"react", "remotion", "../../lib"}

# Patterns that must never appear in generated scene code.
_FORBIDDEN = [
    (re.compile(r"\beval\s*\("), "eval()"),
    (re.compile(r"new\s+Function"), "new Function"),
    (re.compile(r"\bfetch\s*\("), "fetch()"),
    (re.compile(r"\brequire\s*\("), "require()"),
    (re.compile(r"\bimport\s*\("), "dynamic import()"),
    (re.compile(r"\bprocess\b"), "process"),
    (re.compile(r"child_process"), "child_process"),
    (re.compile(r"\bXMLHttpRequest\b"), "XMLHttpRequest"),
    (re.compile(r"\bWebSocket\b"), "WebSocket"),
    (re.compile(r"\b(local|session)Storage\b"), "web storage"),
    (re.compile(r"document\s*\.\s*cookie"), "document.cookie"),
    (re.compile(r'from\s+["\']fs["\']'), "fs import"),
]

_IMPORT_RE = re.compile(r"""^\s*import\s+[^;]*?from\s+['"]([^'"]+)['"]""", re.MULTILINE)


def _load_skill(settings: Settings) -> str:
    global _SKILL_CACHE
    if _SKILL_CACHE is not None:
        return _SKILL_CACHE
    path = settings.repo_root / "apps" / "video-api" / "docs" / "remotion-skill.md"
    _SKILL_CACHE = path.read_text(encoding="utf-8") if path.exists() else "(remotion-skill.md not found)"
    return _SKILL_CACHE


_SYSTEM = """\
You are an expert Remotion (React + TypeScript) animation programmer for educational STEM videos.
Write ONE self-contained scene component. Output ONLY TypeScript/TSX code — no prose, no markdown fences.

Hard rules (a violation makes the scene unusable):
- Export exactly: `export const {KEY}: React.FC<any> = ({{ dur, ...props }}) => {{ ... }}` where {KEY} is the scene key.
- Import ONLY from "react", "remotion", and the project barrel "../../lib". Never import anything else, never read files or the network.
- The scene length in frames is the `dur` prop. Drive every animation from `const frame = useCurrentFrame()` and `const p = frame / dur` (0..1). Do NOT fade the whole scene in/out yourself — the composition's SceneFrame owns the scene envelope and transition; just keep your last beat settling before p≈0.9.
- If `props.cues` (array of number|null) is present, it holds narration-synced reveal ratios per visual item: use `cueOr(cues, i, fallback)` from ../../lib so item i appears when its words are spoken.
- 1920x1080 at 60fps. Wrap content in <AbsoluteFill>. Use `colors`, `mx(x)`, `my(y)` from ../../lib for the dark theme + coordinate mapping (x in [-6,6], y in [-3,3], origin centered, y up).
- Prefer the rich catalog from ../../lib (AmbientBackground, MathFormula, CodeBlock, Plot, TitleBar, Card, Arrow, Caption, TextReveal, BlurReveal, MemoryGrid, FlowToken, BarChart, Counter, Zone, Terminal, KernelBadge, HardwareBox, Icon). Compose a real, topic-specific visual that matches the narration; never leave the frame blank.
- No state, no effects, no timers, no randomness. Pure render from the current frame."""


_SPECIALIST_GUIDANCE = {
    "kinetic_typography": (
        "Use TextReveal/BlurReveal sparingly for one decisive phrase. Keep functional labels stable; "
        "do not turn the whole narration into flying text."
    ),
    "systems_flow": (
        "Build a spatially stable topology with Card/Zone/Arrow, then animate one FlowToken and "
        "focus/dim the currently narrated node. Arrows must not cross labels."
    ),
    "data_visualization": (
        "Use Plot/BarChart/Counter with truthful values and labelled axes. Animate the encoding itself, "
        "not decorative containers, and reveal the comparison when narration reaches it."
    ),
    "code_terminal": (
        "Use CodeBlock or Terminal with real executable-looking content. Reveal by meaningful lines or "
        "command/output beats; never show placeholder code."
    ),
    "memory_model": (
        "Use MemoryGrid for addresses, entries, frames or buffers. Keep indices legible, highlight only "
        "the active cell, and show mapping/translation with an explicit token or arrow."
    ),
    "narrative_motion": (
        "Plan a visible state change at the opening, middle and final narration cues. Settle the last "
        "meaningful state around p=0.88 so the scene never ends as a static afterthought."
    ),
}


def _select_scene_skills(scene: Any) -> list[str]:
    """Small deterministic router inspired by Remotion's official skill-based
    prompt template. Only relevant guidance is injected for a Custom scene."""
    text = " ".join(
        [
            str(getattr(scene, "title", "")),
            str(getattr(scene, "visual_intent", "")),
            str(getattr(scene, "narration", "")),
        ]
    ).lower()
    selected = ["narrative_motion"]
    rules = {
        "systems_flow": ("flow", "path", "pipeline", "kernel", "network", "queue", "layer"),
        "data_visualization": ("plot", "chart", "graph", "metric", "rate", "distribution", "counter"),
        "code_terminal": ("code", "terminal", "command", "shell", "syscall", "function", "algorithm"),
        "memory_model": ("memory", "address", "page table", "buffer", "register", "stack", "heap"),
        "kinetic_typography": ("phrase", "word", "title", "typography", "statement", "reveal"),
    }
    for skill, needles in rules.items():
        if any(needle in text for needle in needles):
            selected.append(skill)
    return selected[:4]


class RemotionSceneCoder:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: Any = None
        self._client_lock = threading.Lock()

    # ------------------------------------------------------------------ LLM
    def _get_client(self) -> Any:
        with self._client_lock:
            if self._client is None:
                from openai import OpenAI

                self._client = OpenAI(
                    api_key=self.settings.openai_api_key,
                    base_url=self.settings.openai_base_url,
                    timeout=self.settings.llm_timeout_seconds,
                    max_retries=self.settings.llm_max_retries,
                )
            return self._client

    def _model(self) -> str:
        return self.settings.scene_coder_model or self.settings.openai_model

    def _extra_body(self) -> dict[str, Any]:
        if self.settings.llm_enable_thinking:
            return {}
        body: dict[str, Any] = {"chat_template_kwargs": {"enable_thinking": False}}
        if "openrouter.ai" in (self.settings.openai_base_url or ""):
            body["reasoning"] = {"effort": "none", "exclude": True}
        return body

    def _call_llm(self, messages: list[dict]) -> str:
        client = self._get_client()
        request: dict[str, Any] = {
            "model": self._model(),
            "temperature": 0.4,
            "max_tokens": self.settings.scene_coder_max_tokens,
            "messages": messages,
        }
        extra = self._extra_body()
        if extra:
            request["extra_body"] = extra
        response = client.chat.completions.create(**request)
        content = response.choices[0].message.content or ""
        if not content.strip():
            raise ValueError(
                f"Remotion scene coder returned empty content (finish_reason={response.choices[0].finish_reason})"
            )
        return content

    def _messages(self, scene: Any, blueprint: Any, previous: str = "", error: str = "") -> list[dict]:
        skill = _load_skill(self.settings)
        selected_skills = _select_scene_skills(scene)
        ctx = {
            "scene_key": scene.key,
            "title": scene.title,
            "narration": scene.narration,
            "visual_intent": scene.visual_intent,
            "duration_seconds": scene.duration_seconds,
            "props": scene.props,
            "video_subject": blueprint.teaching_goal,
            "style_notes": blueprint.style_notes,
            "selected_skills": selected_skills,
        }
        specialist = "\n".join(
            f"- {name}: {_SPECIALIST_GUIDANCE[name]}" for name in selected_skills
        )
        system = (
            _SYSTEM.replace("{KEY}", scene.key)
            + "\n\nSelected specialist guidance:\n"
            + specialist
            + "\n\n"
            + skill
        )
        if previous:
            user = (
                f"The following Remotion scene component for `{scene.key}` failed. Fix it.\n\n"
                f"Scene spec:\n{json.dumps(ctx, indent=2, ensure_ascii=True)}\n\n"
                f"Previous code:\n```tsx\n{previous}\n```\n\nError:\n{error}\n\n"
                f"Output only the corrected component, exported as `{scene.key}`."
            )
        else:
            user = (
                f"Write the scene component for `{scene.key}`.\n\n"
                f"Scene spec:\n{json.dumps(ctx, indent=2, ensure_ascii=True)}\n\n"
                f"Output only the component, exported as `{scene.key}`."
            )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    # ------------------------------------------------------------ entrypoint
    def generate_custom_scenes(self, blueprint: Any, video_dir: Path, materializer: Any) -> None:
        from video_api.pipeline.remotion_materialize import fallback_custom_to_palette

        custom = [s for s in blueprint.scenes if s.is_custom]
        if not custom:
            return
        if not self.settings.scene_coder_enabled or self.settings.fake_llm or not self.settings.openai_api_key:
            logger.info(
                "remotion_scene_coder.skip custom=%d reason=disabled_or_no_llm enabled=%s fake=%s",
                len(custom),
                self.settings.scene_coder_enabled,
                self.settings.fake_llm,
            )
            fallback_custom_to_palette(video_dir, blueprint, {s.key for s in custom})
            return

        remotion_dir = self.settings.repo_root / "apps" / "video-api" / "remotion"
        scene_codes = self._code_scenes_in_waves(custom, blueprint, remotion_dir)
        failed = {scene.key for scene in custom} - set(scene_codes)

        if scene_codes:
            materializer.write_scene_codes(video_dir, blueprint, scene_codes)
        if failed:
            for key in sorted(failed):
                logger.warning(
                    "remotion_scene_coder.fallback scene=%s after %d attempts",
                    key,
                    self.settings.scene_coder_attempts,
                )
            fallback_custom_to_palette(video_dir, blueprint, failed)
        logger.info(
            "remotion_scene_coder.done custom=%d generated=%d fallback=%d",
            len(custom),
            len(scene_codes),
            len(failed),
        )

    def _code_scenes_in_waves(
        self, custom: list[Any], blueprint: Any, remotion_dir: Path
    ) -> dict[str, str]:
        """Generate all Custom scenes in attempt *waves*.

        Per wave: LLM calls for the still-pending scenes run in parallel (I/O
        bound), then ONE `tsc --noEmit` type-checks every candidate of the wave
        at once (instead of a full project check per candidate), then each
        type-clean candidate is proven with a one-frame `remotion still`. Scenes
        that fail carry their code+error into the next wave as repair context.
        """
        scenes_by_key = {scene.key: scene for scene in custom}
        pending = list(custom)
        prev: dict[str, tuple[str, str]] = {}
        scene_codes: dict[str, str] = {}

        for attempt in range(self.settings.scene_coder_attempts):
            if not pending:
                break

            candidates: dict[str, str] = {}
            errors: dict[str, str] = {}

            def _generate(scene: Any) -> str:
                prev_code, prev_error = prev.get(scene.key, ("", ""))
                raw = self._call_llm(self._messages(scene, blueprint, prev_code, prev_error))
                code = _strip_fences(raw)
                _validate_static(code, scene.key)
                return code

            with ThreadPoolExecutor(max_workers=self.settings.llm_parallel) as pool:
                futures = {pool.submit(_generate, scene): scene for scene in pending}
                for future in as_completed(futures):
                    scene = futures[future]
                    try:
                        candidates[scene.key] = future.result()
                    except Exception as exc:
                        errors[scene.key] = str(exc)

            if candidates and self.settings.scene_coder_smoke_render:
                smoke_errors = _batch_smoke_check(
                    candidates,
                    scenes_by_key,
                    remotion_dir,
                    self.settings.scene_coder_smoke_timeout_seconds,
                )
                errors.update(smoke_errors)

            next_pending: list[Any] = []
            for scene in pending:
                key = scene.key
                if key in candidates and key not in errors:
                    scene_codes[key] = candidates[key]
                    logger.info("remotion_scene_coder.success scene=%s attempt=%d", key, attempt)
                else:
                    old_code, _ = prev.get(key, ("", ""))
                    prev[key] = (candidates.get(key) or old_code, errors.get(key, ""))
                    next_pending.append(scene)
                    logger.warning(
                        "remotion_scene_coder.attempt_failed scene=%s attempt=%d error=%s",
                        key,
                        attempt,
                        errors.get(key, "")[:300],
                    )
            pending = next_pending

        return scene_codes


def _strip_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:tsx|typescript|ts|jsx)?[^\n]*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _validate_static(code: str, scene_key: str) -> None:
    if f"export const {scene_key}" not in code:
        raise ValueError(f"scene must export `export const {scene_key}: React.FC<any>`")
    for pattern, label in _FORBIDDEN:
        if pattern.search(code):
            raise ValueError(f"forbidden API in generated scene: {label}")
    for spec in _IMPORT_RE.findall(code):
        if spec not in _ALLOWED_IMPORTS:
            raise ValueError(f"disallowed import: {spec!r} (allowed: react, remotion, ../../lib)")


def _batch_smoke_check(
    candidates: dict[str, str],
    scenes_by_key: dict[str, Any],
    remotion_dir: Path,
    timeout: int,
) -> dict[str, str]:
    """Typecheck a whole wave of candidates with ONE ``tsc --noEmit``, then render
    one frame per type-clean candidate. Returns {scene_key: error} for failures.

    Candidates live under src/jobScenes/<batch_id>/ so their ``../../lib`` import
    resolves exactly as at render time; tsconfig includes ``src``, so a single tsc
    run covers every candidate of the wave. tsc errors are attributed per scene by
    file path in the diagnostic output.
    """
    batch_id = "smoke_" + uuid.uuid4().hex[:12]
    scenes_dir = remotion_dir / "src" / "jobScenes" / batch_id
    entries_dir = remotion_dir / "src" / "entries"
    errors: dict[str, str] = {}
    scenes_dir.mkdir(parents=True, exist_ok=True)
    entries_dir.mkdir(parents=True, exist_ok=True)
    try:
        for key, code in candidates.items():
            (scenes_dir / f"{key}.tsx").write_text(code, encoding="utf-8")

        proc = subprocess.run(
            ["npx", "--no-install", "tsc", "--noEmit"],
            cwd=remotion_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            output = (proc.stdout or "") + "\n" + (proc.stderr or "")
            attributed = False
            for key in candidates:
                marker = f"jobScenes/{batch_id}/{key}.tsx"
                lines = [line for line in output.splitlines() if marker in line]
                if lines:
                    errors[key] = "tsc failed:\n" + "\n".join(lines[:12])
                    attributed = True
            if not attributed:
                # Diagnostics outside any candidate file (should not happen on a
                # healthy project): fail the whole wave conservatively.
                tail = output[-1500:]
                for key in candidates:
                    errors[key] = f"tsc failed (unattributed): {tail}"

        for key, code in candidates.items():
            if key in errors:
                continue
            scene = scenes_by_key[key]
            entry_path = entries_dir / f"{batch_id}_{key}.tsx"
            out_png = entries_dir / f"{batch_id}_{key}.png"
            try:
                props_literal = json.dumps(scene.props or {})
                entry_path.write_text(_smoke_entry(key, batch_id, props_literal), encoding="utf-8")
                _run(
                    [
                        "npx", "--no-install", "remotion", "still",
                        f"src/entries/{batch_id}_{key}.tsx", "Smoke", str(out_png),
                        "--frame=75", "--log=error",
                    ],
                    remotion_dir,
                    timeout,
                    "still",
                )
            except Exception as exc:
                errors[key] = str(exc)
            finally:
                entry_path.unlink(missing_ok=True)
                out_png.unlink(missing_ok=True)
    finally:
        shutil.rmtree(scenes_dir, ignore_errors=True)
    return errors


def _smoke_entry(scene_key: str, smoke_id: str, props_literal: str) -> str:
    return f'''import React from "react";
import {{ Composition, registerRoot }} from "remotion";
import {{ {scene_key} }} from "../jobScenes/{smoke_id}/{scene_key}";

const DUR = 150;
const Wrap: React.FC = () => <{scene_key} dur={{DUR}} {{...({props_literal} as any)}} />;

registerRoot(() => (
  <Composition id="Smoke" component={{Wrap}} fps={{60}} width={{1920}} height={{1080}} durationInFrames={{DUR}} />
));
'''


def _run(cmd: list[str], cwd: Path, timeout: int, label: str) -> None:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-1500:]
        raise RuntimeError(f"{label} failed (exit {proc.returncode}): {tail}")
