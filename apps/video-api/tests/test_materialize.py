from __future__ import annotations

from video_api.pipeline.materialize import slugify


def test_slugify_returns_kebab_case() -> None:
    assert slugify("Math / Derivatives!") == "math-derivatives"
    assert slugify("Biology: Cell Energy!") == "biology-cell-energy"
