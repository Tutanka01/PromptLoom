from __future__ import annotations

import ast
from types import SimpleNamespace

import pytest

from video_api.config import Settings
from video_api.pipeline.scene_coder import (
    SceneCoder,
    _extract_construct_body,
    _validate_body_contract,
    _wrap_in_scaffold,
)
from video_api.pipeline.llm import fake_blueprint


# ---------- _extract_construct_body ----------

def test_extract_body_from_plain_method() -> None:
    raw = """\
def construct(self):
    self.begin_sync()
    bg = make_background()
    self.finish_sync()
"""
    body = _extract_construct_body(raw)
    assert "self.begin_sync()" in body
    assert "def construct" not in body
    assert "make_background()" in body


def test_extract_body_strips_markdown_fence() -> None:
    raw = """\
```python
def construct(self):
    self.begin_sync()
    self.play_until(0.1, FadeIn(bg))
    self.finish_sync()
```"""
    body = _extract_construct_body(raw)
    assert "self.begin_sync()" in body
    assert "```" not in body


def test_extract_body_handles_bare_body() -> None:
    """Some models return just the body lines without the method header."""
    raw = "self.begin_sync()\nbg = make_background()\nself.finish_sync()"
    body = _extract_construct_body(raw)
    assert "self.begin_sync()" in body


def test_extract_body_raises_when_no_construct() -> None:
    raw = "def setup(self):\n    pass\n"
    with pytest.raises(ValueError, match="construct"):
        _extract_construct_body(raw)


def test_extract_body_normalises_indentation() -> None:
    raw = """\
def construct(self):
        self.begin_sync()
        self.finish_sync()
"""
    body = _extract_construct_body(raw)
    # Normalised body should start without leading spaces
    first_line = body.splitlines()[0]
    assert first_line == "self.begin_sync()"


# ---------- _wrap_in_scaffold ----------

def test_wrap_in_scaffold_produces_valid_python() -> None:
    blueprint = fake_blueprint("Explain derivatives", "math")
    scene = blueprint.scenes[0]
    body = "self.begin_sync()\nself.play_until(0.5, FadeIn(bg))\nself.finish_sync()"
    code = _wrap_in_scaffold(scene, body)

    assert f"class {scene.key}(EnglishGeneratedScene):" in code
    assert scene.key in code
    assert "scene_key" in code
    assert "def construct(self):" in code
    assert "self.begin_sync()" in code
    # Must parse cleanly (aside from missing Manim imports)
    # We check structural validity only — strip the Manim-specific names
    ast.parse(code)


def test_wrap_in_scaffold_indents_body() -> None:
    blueprint = fake_blueprint("test", "cs")
    scene = blueprint.scenes[0]
    body = "self.begin_sync()\nself.finish_sync()"
    code = _wrap_in_scaffold(scene, body)
    lines = code.splitlines()
    # The body lines should be indented 8 spaces inside the method
    body_lines = [ln for ln in lines if "self.begin_sync" in ln or "self.finish_sync" in ln]
    for ln in body_lines:
        assert ln.startswith("        "), f"Expected 8-space indent, got: {repr(ln)}"


# ---------- _validate_body_contract ----------

def test_contract_passes_valid_body() -> None:
    body = "self.begin_sync()\nself.play_until(0.5, FadeIn(bg))\nself.finish_sync()"
    _validate_body_contract(body, "Scene1_HookEN")  # no exception


def test_contract_rejects_missing_begin_sync() -> None:
    body = "bg = make_background()\nself.play_until(0.5)\nself.finish_sync()"
    with pytest.raises(ValueError, match="begin_sync"):
        _validate_body_contract(body, "Scene1_HookEN")


def test_contract_rejects_missing_finish_sync() -> None:
    body = "self.begin_sync()\nself.play_until(0.5, FadeIn(bg))"
    with pytest.raises(ValueError, match="finish_sync"):
        _validate_body_contract(body, "Scene1_HookEN")


def test_contract_rejects_missing_play_until() -> None:
    body = "self.begin_sync()\nself.finish_sync()"
    with pytest.raises(ValueError, match="play_until"):
        _validate_body_contract(body, "Scene1_HookEN")


def test_contract_rejects_self_time() -> None:
    body = "self.begin_sync()\nself.play_until(0.5)\nx = self.time\nself.finish_sync()"
    with pytest.raises(ValueError, match="self.time"):
        _validate_body_contract(body, "Scene1_HookEN")


# ---------- round-trip: extract → scaffold → parse ----------

def test_roundtrip_extract_wrap_parses() -> None:
    blueprint = fake_blueprint("Explain OS scheduling", "cs")
    scene = blueprint.scenes[2]

    raw_method = """\
def construct(self):
    self.begin_sync()
    bg = make_background()
    title = title_bar("OS Scheduling")
    node = card("process", width=2.2, color=USER)
    node.move_to(ORIGIN)
    self.add(bg)
    self.play_until(0.12, FadeIn(title))
    self.play_until(0.40, FadeIn(node))
    self.play_until(0.75, node.animate.set_stroke(KERNEL, width=4))
    self.play_until(0.88, FadeIn(t("done", 24, TEXT)))
    self.finish_sync()
    self.play(FadeOut(fade_group(bg, title, node)), run_time=0.7)
"""
    body = _extract_construct_body(raw_method)
    code = _wrap_in_scaffold(scene, body)
    ast.parse(code)  # must produce valid Python AST


def test_scene_coder_empty_content_raises_actionable_error() -> None:
    coder = SceneCoder(Settings(openai_base_url="https://openrouter.ai/api/v1"))
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="length",
                message=SimpleNamespace(content="", reasoning="internal thinking"),
            )
        ]
    )
    coder._get_client = lambda: SimpleNamespace(  # type: ignore[method-assign]
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: response,
            )
        )
    )

    with pytest.raises(ValueError, match="empty content.*finish_reason=length.*reasoning_chars=17"):
        coder._call_llm([{"role": "user", "content": "write code"}])


def test_scene_coder_disables_openrouter_reasoning_by_default() -> None:
    coder = SceneCoder(Settings(openai_base_url="https://openrouter.ai/api/v1"))

    assert coder._extra_body()["reasoning"] == {"effort": "none", "exclude": True}


def test_scene_coder_retries_when_reasoning_cannot_be_disabled() -> None:
    coder = SceneCoder(Settings(openai_base_url="https://openrouter.ai/api/v1"))
    calls = []
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content="def construct(self):\n    self.begin_sync()\n"),
            )
        ]
    )

    def create(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("Reasoning is mandatory for this endpoint and cannot be disabled.")
        return response

    coder._get_client = lambda: SimpleNamespace(  # type: ignore[method-assign]
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )

    assert coder._call_llm([{"role": "user", "content": "write code"}]).startswith("def construct")
    assert "reasoning" in calls[0]["extra_body"]
    assert "reasoning" not in calls[1]["extra_body"]
