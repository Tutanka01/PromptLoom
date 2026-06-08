from __future__ import annotations

import pytest

from video_api.pipeline import validate
from video_api.pipeline.validate import (
    smoke_render_scene,
    validate_scene_names,
)


_MODULE = """\
from manim import *


class Scene1_HookEN(Base):
    def construct(self):
        self.begin_sync()
        items = [Dot() for _ in range(3)]
        for item in items:
            self.add(item)
        with self.voiceover() as tracker:
            tracker.note = item
        self.play_until(0.5, FadeIn(items[0]))
{extra}
        self.finish_sync()
"""


def _module(extra: str = "") -> str:
    return _MODULE.format(extra=extra)


def test_undefined_name_is_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(validate, "manim_namespace", lambda: {"Base", "Dot", "FadeIn"})
    code = _module("        glow_present = GlowDots(items[0])")
    with pytest.raises(ValueError, match="GlowDots"):
        validate_scene_names(code, "Scene1_HookEN")


def test_valid_names_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    # Locals bound by assignment, for-targets, comprehension vars and with-as must
    # all be treated as defined — over-approximation guards against false positives.
    monkeypatch.setattr(validate, "manim_namespace", lambda: {"Base", "Dot", "FadeIn"})
    validate_scene_names(_module(), "Scene1_HookEN")


def test_skips_when_manim_unavailable_with_star_import(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(validate, "manim_namespace", lambda: None)
    code = _module("        glow_present = GlowDots(items[0])")
    # No manim namespace + `from manim import *` → cannot resolve names, so do not
    # risk a false positive; the smoke render remains the runtime guarantee.
    validate_scene_names(code, "Scene1_HookEN")


def test_smoke_render_skips_without_manim(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(validate, "manim_namespace", lambda: None)
    smoke_render_scene(tmp_path, "Scene1_HookEN", _module(), timeout_seconds=5)
    assert not (tmp_path / "_smoke_Scene1_HookEN.py").exists()
