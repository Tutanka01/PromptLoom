from __future__ import annotations

from pathlib import Path

from video_api.config import Settings
from video_api.pipeline.llm import fake_blueprint
from video_api.pipeline.materialize import Materializer
from video_api.pipeline.validate import validate_static_video_source

# Derive the actual repo root from this file's location:
# tests/ → video-api/ → apps/ → repo-root
_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_generated_manim_uses_renderer_time_compatibility(tmp_path: Path) -> None:
    settings = Settings(repo_root=_REPO_ROOT)
    video_dir = Materializer(settings).materialize(
        fake_blueprint("Explain derivatives", "math"),
        tmp_path,
    )

    validate_static_video_source(video_dir)
    manim_path = next(path for path in video_dir.glob("*_en.py") if path.name != "generate_voice_en.py")
    manim_source = manim_path.read_text(encoding="utf-8")

    assert "def now(self):" in manim_source
    assert "self._sync_start = self.now()" in manim_source
    assert "self.time" not in manim_source
    assert 'layout_name = "concept_map"' in manim_source
    assert 'layout_name = "equation_transform"' in manim_source
    assert 'layout_name = "graph_plot"' in manim_source
    # No placeholder/template residue text should ever be drawn on screen.
    for ghost in ("structured comparison", "recap map", "sequence over time", "explanation path"):
        assert ghost not in manim_source

    render_script = (video_dir / "render_en.sh").read_text(encoding="utf-8")
    assert "media/videos/prompt_to_academic_video_en/${QUALITY_DIR}/Scene1_HookEN.mp4" in render_script

    assemble_script = (video_dir / "assemble_en.sh").read_text(encoding="utf-8")
    assert "apad" in assemble_script, "assemble script must pad audio to prevent truncation"
    assert "-shortest" in assemble_script

    voice_script = (video_dir / "generate_voice_en.py").read_text(encoding="utf-8")
    assert '"openai"' in voice_script
    assert "client.audio.speech.create" in voice_script

    plan = next(tmp_path.glob("docs/videos/math/prompt-to-academic-video/plan.md")).read_text(encoding="utf-8")
    assert "Area: math" in plan
    assert "## Learning Objectives" in plan
