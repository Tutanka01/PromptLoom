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
import subprocess
import uuid
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
- The scene length in frames is the `dur` prop. Drive every animation from `const frame = useCurrentFrame()` and `const p = frame / dur` (0..1). Fade the whole scene out near p=1 (use `tailFade(p)` from ../../lib).
- 1920x1080 at 60fps. Wrap content in <AbsoluteFill>. Use `colors`, `mx(x)`, `my(y)` from ../../lib for the dark theme + coordinate mapping (x in [-6,6], y in [-3,3], origin centered, y up).
- Prefer the rich catalog from ../../lib (AmbientBackground, MathFormula, CodeBlock, Plot, TitleBar, Card, Arrow, Caption, TextReveal, BlurReveal). Compose a real, topic-specific visual that matches the narration; never leave the frame blank.
- No state, no effects, no timers, no randomness. Pure render from the current frame."""


class RemotionSceneCoder:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: Any = None

    # ------------------------------------------------------------------ LLM
    def _get_client(self) -> Any:
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
        ctx = {
            "scene_key": scene.key,
            "title": scene.title,
            "narration": scene.narration,
            "visual_intent": scene.visual_intent,
            "duration_seconds": scene.duration_seconds,
            "props": scene.props,
            "video_subject": blueprint.teaching_goal,
            "style_notes": blueprint.style_notes,
        }
        system = _SYSTEM.replace("{KEY}", scene.key) + "\n\n" + skill
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
        scene_codes: dict[str, str] = {}
        failed: set[str] = set()
        for scene in custom:
            code = self._code_one_scene(scene, blueprint, remotion_dir)
            if code is not None:
                scene_codes[scene.key] = code
            else:
                failed.add(scene.key)

        if scene_codes:
            materializer.write_scene_codes(video_dir, blueprint, scene_codes)
        if failed:
            fallback_custom_to_palette(video_dir, blueprint, failed)
        logger.info(
            "remotion_scene_coder.done custom=%d generated=%d fallback=%d",
            len(custom),
            len(scene_codes),
            len(failed),
        )

    def _code_one_scene(self, scene: Any, blueprint: Any, remotion_dir: Path) -> str | None:
        prev_code = ""
        prev_error = ""
        for attempt in range(self.settings.scene_coder_attempts):
            try:
                raw = self._call_llm(self._messages(scene, blueprint, prev_code, prev_error))
                code = _strip_fences(raw)
                _validate_static(code, scene.key)
                if self.settings.scene_coder_smoke_render:
                    _smoke_check(
                        code,
                        scene,
                        remotion_dir,
                        self.settings.scene_coder_smoke_timeout_seconds,
                    )
                logger.info("remotion_scene_coder.success scene=%s attempt=%d", scene.key, attempt)
                return code
            except Exception as exc:
                prev_code = locals().get("code", prev_code) or prev_code
                prev_error = str(exc)
                logger.warning(
                    "remotion_scene_coder.attempt_failed scene=%s attempt=%d error=%s",
                    scene.key,
                    attempt,
                    str(exc)[:300],
                )
        logger.warning("remotion_scene_coder.fallback scene=%s after %d attempts", scene.key, self.settings.scene_coder_attempts)
        return None


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


def _smoke_check(code: str, scene: Any, remotion_dir: Path, timeout: int) -> None:
    """Typecheck the project with the candidate in place, then render one frame.

    The candidate is placed under src/jobScenes/<smoke_id>/ so its ``../../lib``
    import resolves exactly as it will at render time. A throwaway entry exposes a
    ``Smoke`` composition rendering the scene with its real props.
    """
    smoke_id = "smoke_" + uuid.uuid4().hex[:12]
    scenes_dir = remotion_dir / "src" / "jobScenes" / smoke_id
    entry_path = remotion_dir / "src" / "entries" / f"{smoke_id}.tsx"
    out_png = remotion_dir / "src" / "entries" / f"{smoke_id}.png"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    entry_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        (scenes_dir / f"{scene.key}.tsx").write_text(code, encoding="utf-8")
        props_literal = json.dumps(scene.props or {})
        entry_path.write_text(_smoke_entry(scene.key, smoke_id, props_literal), encoding="utf-8")

        _run(["npx", "--no-install", "tsc", "--noEmit"], remotion_dir, timeout, "tsc")
        _run(
            [
                "npx", "--no-install", "remotion", "still",
                f"src/entries/{smoke_id}.tsx", "Smoke", str(out_png),
                "--frame=75", "--log=error",
            ],
            remotion_dir,
            timeout,
            "still",
        )
    finally:
        import shutil as _sh

        _sh.rmtree(scenes_dir, ignore_errors=True)
        entry_path.unlink(missing_ok=True)
        out_png.unlink(missing_ok=True)


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
