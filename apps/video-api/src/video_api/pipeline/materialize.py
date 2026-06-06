from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path

from video_api.config import Settings
from video_api.schemas import SceneSpec, VideoBlueprint


logger = logging.getLogger(__name__)


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return re.sub(r"-+", "-", value) or "video"


def _short(value: str, limit: int = 30) -> str:
    compact = " ".join(value.replace("\n", " ").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "."


def _py(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _plan_markdown(blueprint: VideoBlueprint) -> str:
    scene_lines = "\n".join(
        f"- `{scene.key}`: {scene.title} - {scene.visual_intent}" for scene in blueprint.scenes
    )
    return f"""# {blueprint.title}

## Topic

{blueprint.teaching_goal}

## Audience

{blueprint.audience}

## Visual Style

{blueprint.style_notes}

## Scenes

{scene_lines}

## Acceptance Criteria

- Every segment has matching narration, beats, and a Manim scene.
- Chatterbox main non-turbo voice is generated or reused.
- Final video passes ffprobe, freezedetect, and snapshot extraction.
"""


def _script_markdown(blueprint: VideoBlueprint) -> str:
    sections = []
    for scene in blueprint.scenes:
        sections.append(f"## {scene.key}: {scene.title}\n\n{scene.text}\n")
    return f"# {blueprint.title} Script\n\n" + "\n".join(sections)


def _segments_json(blueprint: VideoBlueprint) -> dict:
    return {
        "segments": [
            {
                "key": scene.key,
                "class": scene.key,
                "title": scene.title,
                "text": scene.text,
            }
            for scene in blueprint.scenes
        ]
    }


def _beats_json(blueprint: VideoBlueprint) -> dict:
    return {scene.key: [beat.model_dump() for beat in scene.beats] for scene in blueprint.scenes}


def _scene_code(scene: SceneSpec) -> str:
    beat_cards = [_short(beat.visual_action, 28) for beat in scene.beats[:4]]
    while len(beat_cards) < 4:
        beat_cards.append(_short(scene.visual_intent, 28))
    summary = _short(scene.visual_intent, 58)
    return f'''

class {scene.key}(EnglishGeneratedScene):
    scene_key = {_py(scene.key)}
    fallback_duration = 32

    def construct(self):
        self.begin_sync()
        bg = make_background()
        title = title_bar({_py(scene.title)})
        left = code_card({_py(beat_cards[0])}, width=3.35, color=USER).move_to(LEFT * 3.7 + UP * 0.55)
        middle = card({_py(beat_cards[1])}, width=3.15, color=KERNEL).move_to(ORIGIN + UP * 0.55)
        right = card({_py(beat_cards[2])}, width=3.35, color=SUCCESS).move_to(RIGHT * 3.7 + UP * 0.55)
        lower = card({_py(beat_cards[3])}, width=4.4, height=0.88, color=PURPLE, font_size=20).move_to(DOWN * 1.55)
        path_a = connect(left, middle, USER)
        path_b = connect(middle, right, KERNEL)
        dot = flow_dot(path_a, KERNEL)
        summary = t({_py(summary)}, 28, TEXT, BOLD).to_edge(DOWN, buff=0.58)

        self.add(bg)
        self.play_until(0.08, FadeIn(title), FadeIn(left, shift=UP * 0.12))
        self.play_until(0.32, FadeIn(middle, shift=UP * 0.12), Create(path_a), FadeIn(dot))
        self.play_until(0.56, MoveAlongPath(dot, path_a), FadeIn(right, shift=UP * 0.12), Create(path_b), rate_func=linear)
        self.play_until(0.76, MoveAlongPath(dot, path_b), FadeIn(lower, shift=UP * 0.12), dim(left), undim(right), rate_func=linear)
        self.play_until(0.88, FadeIn(summary), middle.animate.set_stroke(KERNEL, width=4))
        self.finish_sync()
        self.play(FadeOut(fade_group(bg, title, left, middle, right, lower, path_a, path_b, dot, summary)), run_time=0.7)
'''


def _manim_code(blueprint: VideoBlueprint, slug_module: str) -> str:
    scenes = "\n".join(_scene_code(scene) for scene in blueprint.scenes)
    return f'''import json
from pathlib import Path

from manim import *

from {slug_module}_style import (
    BG,
    PURPLE,
    KERNEL,
    SUCCESS,
    TEXT,
    USER,
    card,
    code_card,
    connect,
    dim,
    flow_dot,
    make_background,
    t,
    title_bar,
    undim,
)


ROOT = Path(__file__).resolve().parent
DURATIONS_FILE = ROOT / "audio" / "en" / "durations.json"
SEGMENTS_FILE = ROOT / "segments_en.json"


def load_json(path, fallback):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return fallback


def load_segments():
    data = load_json(SEGMENTS_FILE, {{"segments": []}})
    return {{segment["key"]: segment["text"] for segment in data["segments"]}}


DURATIONS = load_json(DURATIONS_FILE, {{}})
SEGMENT_TEXT = load_segments()


def duration(key, fallback):
    return float(DURATIONS.get(key, fallback))


def fade_group(*items):
    return VGroup(*[item for item in items if item is not None])


class EnglishGeneratedScene(Scene):
    scene_key = ""
    fallback_duration = 35.0

    def setup(self):
        self.camera.background_color = BG

    def begin_sync(self):
        self._sync_start = self.time
        self._scene_duration = duration(self.scene_key, self.fallback_duration)
        text = SEGMENT_TEXT.get(self.scene_key)
        if text:
            self.add_subcaption(text, duration=self._scene_duration)

    def scene_duration(self):
        return getattr(self, "_scene_duration", duration(self.scene_key, self.fallback_duration))

    def cue(self, ratio):
        return self._sync_start + self.scene_duration() * ratio

    def hold_until(self, ratio):
        self.wait(max(0, self.cue(ratio) - self.time))

    def play_until(self, ratio, *animations, min_run_time=0.25, rate_func=smooth):
        run_time = max(min_run_time, self.cue(ratio) - self.time)
        self.play(*animations, run_time=run_time, rate_func=rate_func)

    def finish_sync(self, trailing_animation=0.7):
        target = self.scene_duration()
        elapsed = self.time - self._sync_start
        self.wait(max(0, target - elapsed - trailing_animation))
{scenes}
'''


def _render_script(blueprint: VideoBlueprint, slug_module: str) -> str:
    scene_lines = "\n".join(f"  {scene.key}" for scene in blueprint.scenes)
    concat_lines = "\n".join(
        f"file 'media/videos/{slug_module}/${{QUALITY_DIR}}/{scene.key}.mp4'"
        for scene in blueprint.scenes
    )
    return f'''#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

QUALITY="${{QUALITY:-qm}}"
SCENES=(
{scene_lines}
)

if [[ "${{MANIM_USE_UV:-1}}" == "1" ]]; then
  uv run --with manim python -m manim "-${{QUALITY}}" {slug_module}_en.py "${{SCENES[@]}}"
else
  python -m manim "-${{QUALITY}}" {slug_module}_en.py "${{SCENES[@]}}"
fi

QUALITY_DIR="720p30"
if [[ "${{QUALITY}}" == "ql" ]]; then
  QUALITY_DIR="480p15"
elif [[ "${{QUALITY}}" == "qh" ]]; then
  QUALITY_DIR="1080p60"
fi

cat > concat_en.txt <<EOF
{concat_lines}
EOF

mkdir -p final
ffmpeg -y -f concat -safe 0 -i concat_en.txt -c copy final/{blueprint.slug}-en-silent.mp4
'''


def _assemble_script(blueprint: VideoBlueprint) -> str:
    return f'''#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

VIDEO="${{VIDEO:-final/{blueprint.slug}-en-silent.mp4}}"
AUDIO="${{AUDIO:-audio/en/voiceover_en.mp3}}"
OUTPUT="${{OUTPUT:-final/{blueprint.slug}-en-final.mp4}}"

ffmpeg -y \\
  -i "${{VIDEO}}" \\
  -i "${{AUDIO}}" \\
  -map 0:v:0 \\
  -map 1:a:0 \\
  -c:v copy \\
  -c:a aac \\
  -b:a 192k \\
  -shortest \\
  "${{OUTPUT}}"

echo "Wrote ${{OUTPUT}}"
'''


class Materializer:
    def __init__(self, settings: Settings):
        self.settings = settings

    def materialize(self, blueprint: VideoBlueprint, workspace: Path) -> Path:
        theme = slugify(blueprint.theme)
        slug_module = blueprint.slug.replace("-", "_")
        docs_dir = workspace / "docs" / "videos" / theme / blueprint.slug
        video_dir = workspace / "videos" / theme / blueprint.slug
        logger.info(
            "materialize.start title=%s theme=%s slug=%s scenes=%d workspace=%s",
            blueprint.title,
            theme,
            blueprint.slug,
            len(blueprint.scenes),
            workspace,
        )
        docs_dir.mkdir(parents=True, exist_ok=True)
        video_dir.mkdir(parents=True, exist_ok=True)
        for generated_name in ["audio", "media", "final", "renders"]:
            generated_path = video_dir / generated_name
            if generated_path.exists():
                shutil.rmtree(generated_path)
        for concat_path in video_dir.glob("concat*.txt"):
            concat_path.unlink()

        (docs_dir / "plan.md").write_text(_plan_markdown(blueprint), encoding="utf-8")
        (docs_dir / "script.md").write_text(_script_markdown(blueprint), encoding="utf-8")
        (video_dir / "segments_en.json").write_text(
            json.dumps(_segments_json(blueprint), indent=2) + "\n",
            encoding="utf-8",
        )
        (video_dir / "beats_en.json").write_text(
            json.dumps(_beats_json(blueprint), indent=2) + "\n",
            encoding="utf-8",
        )

        style_src = self.settings.repo_root / "docs" / "boilerplate" / "video" / "video_style.py"
        shutil.copyfile(style_src, video_dir / f"{slug_module}_style.py")

        voice_src = (
            self.settings.repo_root
            / "videos"
            / "linux-fondamentaux"
            / "002-c-est-quoi-un-syscall"
            / "generate_voice_en.py"
        )
        if not voice_src.exists():
            raise FileNotFoundError(f"Missing reference voice generator: {voice_src}")
        shutil.copyfile(voice_src, video_dir / "generate_voice_en.py")

        (video_dir / f"{slug_module}_en.py").write_text(
            _manim_code(blueprint, slug_module),
            encoding="utf-8",
        )
        render_path = video_dir / "render_en.sh"
        assemble_path = video_dir / "assemble_en.sh"
        render_path.write_text(_render_script(blueprint, slug_module), encoding="utf-8")
        assemble_path.write_text(_assemble_script(blueprint), encoding="utf-8")
        render_path.chmod(0o755)
        assemble_path.chmod(0o755)
        logger.info(
            "materialize.done docs_dir=%s video_dir=%s manim_file=%s render=%s assemble=%s",
            docs_dir,
            video_dir,
            video_dir / f"{slug_module}_en.py",
            render_path,
            assemble_path,
        )
        return video_dir
