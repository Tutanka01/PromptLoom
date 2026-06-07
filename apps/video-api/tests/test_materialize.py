from __future__ import annotations

from pathlib import Path

from video_api.config import Settings
from video_api.pipeline.llm import fake_blueprint
from video_api.pipeline.materialize import Materializer
from video_api.pipeline.materialize import slugify


def test_slugify_returns_kebab_case() -> None:
    assert slugify("Math / Derivatives!") == "math-derivatives"
    assert slugify("Biology: Cell Energy!") == "biology-cell-energy"


def test_materialized_style_connect_accepts_points(tmp_path) -> None:
    settings = Settings(repo_root=Path(__file__).resolve().parents[3])
    video_dir = Materializer(settings).materialize(
        fake_blueprint("Explain Markov chains", "markov-chains", target_duration_seconds=75),
        tmp_path,
    )

    style_text = next(video_dir.glob("*_style.py")).read_text(encoding="utf-8")

    assert "def _anchor_point" in style_text
    assert "hasattr(value, \"get_boundary_point\")" in style_text
