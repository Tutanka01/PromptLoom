from __future__ import annotations

import ast

import pytest

from video_api.pipeline.scene_coder import (
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
