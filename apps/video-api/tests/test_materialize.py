from __future__ import annotations

from video_api.pipeline.materialize import slugify


def test_slugify_returns_kebab_case() -> None:
    assert slugify("Linux Fondamentaux / Page Tables!") == "linux-fondamentaux-page-tables"
