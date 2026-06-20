from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import pytest

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
    assert "TRANSITION_SFX" in assemble_script
    assert (video_dir / "build_transition_sfx.py").exists()

    voice_script = (video_dir / "generate_voice_en.py").read_text(encoding="utf-8")
    assert '"openai"' in voice_script
    assert "client.audio.speech.create" in voice_script

    plan = next(tmp_path.glob("docs/videos/math/prompt-to-academic-video/plan.md")).read_text(encoding="utf-8")
    assert "Area: math" in plan
    assert "## Learning Objectives" in plan


def test_transition_sfx_builder_is_bounded_and_writes_pcm(tmp_path: Path) -> None:
    settings = Settings(repo_root=_REPO_ROOT)
    video_dir = Materializer(settings).materialize(
        fake_blueprint("Explain sound bridges", "media"),
        tmp_path,
    )
    audio_dir = video_dir / "audio" / "en"
    audio_dir.mkdir(parents=True, exist_ok=True)
    (audio_dir / "durations.json").write_text(
        json.dumps({"Scene1_HookEN": 0.25, "Scene2_DefinitionEN": 0.25}),
        encoding="utf-8",
    )

    subprocess.run(
        [sys.executable, "build_transition_sfx.py"],
        cwd=video_dir,
        check=True,
        capture_output=True,
        text=True,
    )

    output = audio_dir / "transition_sfx.wav"
    with wave.open(str(output), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 48000
        assert wav.getnframes() == 48000


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is required")
def test_transition_sfx_assembly_is_finite(tmp_path: Path) -> None:
    settings = Settings(repo_root=_REPO_ROOT)
    blueprint = fake_blueprint("Explain sound bridges", "media")
    video_dir = Materializer(settings).materialize(blueprint, tmp_path)
    audio_dir = video_dir / "audio" / "en"
    audio_dir.mkdir(parents=True, exist_ok=True)
    (audio_dir / "durations.json").write_text(
        json.dumps({scene.key: 0.125 for scene in blueprint.scenes}),
        encoding="utf-8",
    )
    silent = video_dir / "final" / f"{blueprint.slug}-en-silent.mp4"
    silent.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x180:d=1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(silent),
        ],
        check=True,
        capture_output=True,
        timeout=15,
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=330:duration=1",
            "-q:a", "5", str(audio_dir / "voiceover_en.mp3"),
        ],
        check=True,
        capture_output=True,
        timeout=15,
    )
    subprocess.run(
        ["./assemble_en.sh"],
        cwd=video_dir,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
        env={**os.environ, "TRANSITION_SFX": "1"},
    )
    output = video_dir / "final" / f"{blueprint.slug}-en-final.mp4"
    assert output.exists()
    assert output.stat().st_size < 5 * 1024 * 1024
