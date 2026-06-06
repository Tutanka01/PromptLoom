from __future__ import annotations

import ast
import json
import logging
import re
from pathlib import Path
from typing import Any

from video_api.config import Settings
from video_api.schemas import SceneSpec, VideoBlueprint


logger = logging.getLogger(__name__)

_SKILL_CACHE: str | None = None


def _load_manim_skill(settings: Settings) -> str:
    global _SKILL_CACHE
    if _SKILL_CACHE is not None:
        return _SKILL_CACHE
    path = settings.repo_root / "apps" / "video-api" / "docs" / "manim-skill.md"
    if path.exists():
        _SKILL_CACHE = path.read_text(encoding="utf-8")
    else:
        _SKILL_CACHE = "(manim-skill.md not found)"
    return _SKILL_CACHE


_SCENE_CODER_SYSTEM = """\
You are an expert Manim animation programmer writing educational explainer videos.
Follow the Manim Skill document exactly. Output ONLY the `def construct(self):` method — \
no class definition, no imports, no extra prose.
Start your response with `def construct(self):` and indent the body with 4 spaces.
Never include import statements. Never call open(), eval(), exec(), or os/subprocess functions."""


def _strip_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:python)?[^\n]*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _extract_construct_body(raw: str) -> str:
    """Return the unindented body lines of construct() from LLM output.

    Tries AST first, falls back to regex. Raises ValueError if not found.
    """
    code = _strip_fences(raw)

    # Ensure there's a def construct to parse
    if "def construct" not in code:
        # Maybe the model returned just the body (no method header)
        if code.strip().startswith("self.begin_sync"):
            return code.strip()
        raise ValueError("LLM output does not contain 'def construct'")

    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "construct":
                lines = code.splitlines()
                body_start = node.body[0].lineno - 1
                body_end = node.end_lineno
                body_lines = lines[body_start:body_end]
                non_empty = [ln for ln in body_lines if ln.strip()]
                if not non_empty:
                    raise ValueError("construct() body is empty")
                min_indent = min(len(ln) - len(ln.lstrip()) for ln in non_empty)
                return "\n".join(ln[min_indent:] if ln.strip() else "" for ln in body_lines)
    except SyntaxError:
        pass

    # Regex fallback: capture everything indented after `def construct(self):`
    match = re.search(r"def construct\s*\(self\)\s*:[^\n]*\n((?:[ \t]+[^\n]*\n?)+)", code)
    if match:
        body = match.group(1)
        body_lines = body.splitlines()
        non_empty = [ln for ln in body_lines if ln.strip()]
        if not non_empty:
            raise ValueError("construct() body is empty (regex fallback)")
        min_indent = min(len(ln) - len(ln.lstrip()) for ln in non_empty)
        return "\n".join(ln[min_indent:] if ln.strip() else "" for ln in body_lines)

    raise ValueError("Could not extract construct() body from LLM output")


def _py(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _wrap_in_scaffold(scene: SceneSpec, body: str) -> str:
    """Wrap a construct() body in the full class definition scaffold."""
    indented = "\n".join(
        "        " + line if line.strip() else ""
        for line in body.splitlines()
    )
    return f"""
class {scene.key}(EnglishGeneratedScene):
    scene_key = {_py(scene.key)}
    fallback_duration = {scene.duration_seconds}

    def construct(self):
{indented}
"""


class SceneCoder:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError("openai package required for scene coding") from exc
            model = self.settings.scene_coder_model or self.settings.openai_model
            self._client = OpenAI(
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                timeout=self.settings.llm_timeout_seconds,
            )
        return self._client

    def _model(self) -> str:
        return self.settings.scene_coder_model or self.settings.openai_model

    def _call_llm(self, messages: list[dict]) -> str:
        client = self._get_client()
        kwargs: dict[str, Any] = {}
        if self.settings.llm_response_format == "json_object":
            # Scene coder does NOT need JSON mode — it returns Python code
            pass
        response = client.chat.completions.create(
            model=self._model(),
            temperature=0.25,
            max_tokens=2048,
            messages=messages,
        )
        return response.choices[0].message.content or ""

    def _build_scene_context(self, scene: SceneSpec, blueprint: VideoBlueprint) -> dict:
        return {
            "scene_key": scene.key,
            "title": scene.title,
            "layout": scene.layout,
            "duration_seconds": scene.duration_seconds,
            "narration": scene.text,
            "visual_intent": scene.visual_intent,
            "beats": [
                {"at": beat.at, "text_hint": beat.text_hint, "visual_action": beat.visual_action}
                for beat in scene.beats
            ],
            "video_subject": blueprint.teaching_goal,
            "style_notes": blueprint.style_notes,
        }

    def generate(self, scene: SceneSpec, blueprint: VideoBlueprint) -> str:
        """Generate the full class code for a single scene. Returns a class definition string."""
        if self.settings.fake_llm or not self.settings.openai_api_key:
            raise RuntimeError("SceneCoder requires a real LLM (fake_llm=True disables it)")

        skill = _load_manim_skill(self.settings)
        scene_ctx = self._build_scene_context(scene, blueprint)
        logger.info(
            "scene_coder.generate scene=%s layout=%s beats=%d",
            scene.key,
            scene.layout,
            len(scene.beats),
        )
        messages = [
            {"role": "system", "content": f"{_SCENE_CODER_SYSTEM}\n\n{skill}"},
            {
                "role": "user",
                "content": (
                    f"Write the `def construct(self):` method for this scene.\n"
                    f"Scene specification (JSON):\n{json.dumps(scene_ctx, indent=2, ensure_ascii=True)}\n\n"
                    f"Output only the method. Start with `def construct(self):`. "
                    f"Indent body with 4 spaces. No imports. No class header."
                ),
            },
        ]
        raw = self._call_llm(messages)
        logger.info("scene_coder.generate.done scene=%s response_chars=%d", scene.key, len(raw))
        body = _extract_construct_body(raw)
        _validate_body_contract(body, scene.key)
        return _wrap_in_scaffold(scene, body)

    def repair(self, scene: SceneSpec, blueprint: VideoBlueprint, previous_code: str, error: str) -> str:
        """Attempt to fix a previously generated scene that failed validation or AST check."""
        if self.settings.fake_llm or not self.settings.openai_api_key:
            raise RuntimeError("SceneCoder requires a real LLM")

        skill = _load_manim_skill(self.settings)
        scene_ctx = self._build_scene_context(scene, blueprint)
        logger.info(
            "scene_coder.repair scene=%s error_chars=%d",
            scene.key,
            len(error),
        )
        messages = [
            {"role": "system", "content": f"{_SCENE_CODER_SYSTEM}\n\n{skill}"},
            {
                "role": "user",
                "content": (
                    f"The following Manim `def construct(self):` method has an error. Fix it.\n\n"
                    f"Scene specification:\n{json.dumps(scene_ctx, indent=2, ensure_ascii=True)}\n\n"
                    f"Previous (broken) code:\n```python\n{previous_code}\n```\n\n"
                    f"Error:\n{error}\n\n"
                    f"Output only the corrected `def construct(self):` method. "
                    f"Indent body with 4 spaces. No imports. No class header."
                ),
            },
        ]
        raw = self._call_llm(messages)
        logger.info("scene_coder.repair.done scene=%s response_chars=%d", scene.key, len(raw))
        body = _extract_construct_body(raw)
        _validate_body_contract(body, scene.key)
        return _wrap_in_scaffold(scene, body)


def _validate_body_contract(body: str, scene_key: str) -> None:
    """Raise ValueError if the construct body violates structural contracts."""
    if "self.begin_sync()" not in body:
        raise ValueError(f"construct() body for {scene_key} missing self.begin_sync()")
    if "self.finish_sync()" not in body:
        raise ValueError(f"construct() body for {scene_key} missing self.finish_sync()")
    if "self.play_until(" not in body:
        raise ValueError(f"construct() body for {scene_key} has no self.play_until() calls")
    if "self.time" in body and "self.now()" not in body:
        raise ValueError(
            f"construct() body for {scene_key} uses deprecated self.time — use self.now()"
        )
