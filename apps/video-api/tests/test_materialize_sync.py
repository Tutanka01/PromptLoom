from __future__ import annotations

from pathlib import Path

from video_api.config import Settings
from video_api.pipeline.llm import fake_blueprint
from video_api.pipeline.materialize import Materializer
from video_api.pipeline.validate import validate_static_video_source


def test_generated_manim_uses_renderer_time_compatibility(tmp_path: Path) -> None:
    settings = Settings(repo_root=Path("/workspace"))
    video_dir = Materializer(settings).materialize(
        fake_blueprint("Explain page tables", "linux-fondamentaux"),
        tmp_path,
    )

    validate_static_video_source(video_dir)
    manim_path = next(path for path in video_dir.glob("*_en.py") if path.name != "generate_voice_en.py")
    manim_source = manim_path.read_text(encoding="utf-8")

    assert "def now(self):" in manim_source
    assert "self._sync_start = self.now()" in manim_source
    assert "self.time" not in manim_source

    render_script = (video_dir / "render_en.sh").read_text(encoding="utf-8")
    assert "media/videos/prompt_to_kernel_video_en/${QUALITY_DIR}/Scene1_HookEN.mp4" in render_script
