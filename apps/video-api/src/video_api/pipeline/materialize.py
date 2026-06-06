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
        f"- `{scene.key}` ({scene.duration_seconds}s, `{scene.layout}`): "
        f"{scene.title} - {scene.visual_intent}"
        for scene in blueprint.scenes
    )
    return f"""# {blueprint.title}

## Topic

{blueprint.teaching_goal}

## Audience

{blueprint.audience}

## Visual Style

{blueprint.style_notes}

## Duration

Target: {blueprint.target_duration_seconds} seconds.

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
    beat_cards = [_short(beat.visual_action, 30) for beat in scene.beats[:5]]
    while len(beat_cards) < 5:
        beat_cards.append(_short(scene.visual_intent, 30))
    summary = _short(scene.visual_intent, 58)
    return f'''

class {scene.key}(EnglishGeneratedScene):
    scene_key = {_py(scene.key)}
    fallback_duration = {scene.duration_seconds}

    def construct(self):
        self.begin_sync()
        bg = make_background()
        title = title_bar({_py(scene.title)})
        layout = build_layout({_py(scene.layout)}, {_py(beat_cards)}, {_py(summary)})

        self.add(bg)
        self.play_until(0.08, FadeIn(title))
        self.play_until(0.24, FadeIn(layout["stage"], shift=UP * 0.10), FadeIn(layout["primary"], shift=UP * 0.12))
        self.play_until(0.42, FadeIn(layout["secondary"], shift=UP * 0.12), Create(layout["path_a"]))
        self.play_until(0.60, FadeIn(layout["moving"]), MoveAlongPath(layout["moving"], layout["path_a"]), FadeIn(layout["tertiary"], shift=UP * 0.12), rate_func=linear)
        self.play_until(0.76, MoveAlongPath(layout["moving"], layout["path_b"]), FadeIn(layout["quaternary"], shift=UP * 0.12), dim(layout["primary"]), rate_func=linear)
        self.play_until(0.88, FadeIn(layout["summary"]), undim(layout["primary"]), layout["focus"].animate.set_stroke(KERNEL, width=4))
        self.finish_sync()
        self.play(FadeOut(fade_group(bg, title, layout["all"])), run_time=0.7)
'''


def _manim_code(blueprint: VideoBlueprint, slug_module: str) -> str:
    scenes = "\n".join(_scene_code(scene) for scene in blueprint.scenes)
    return f'''import json
from pathlib import Path

from manim import *

from {slug_module}_style import (
    BG,
    DANGER,
    EDGE,
    HARDWARE,
    PURPLE,
    KERNEL,
    MUTED,
    PANEL_2,
    SUCCESS,
    TEXT,
    USER,
    card,
    code_card,
    connect,
    dim,
    flow_dot,
    make_background,
    mono,
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


def _label(labels, index, fallback):
    if index < len(labels) and labels[index]:
        return labels[index]
    return fallback


def _small_card(label, color=USER, width=2.35):
    return card(label, width=width, height=0.72, color=color, font_size=18)


def _zone(label, color, center):
    box = RoundedRectangle(width=5.6, height=1.62, corner_radius=0.14, color=color, stroke_width=2)
    box.set_fill(PANEL_2, opacity=0.38).move_to(center)
    text = t(label, 18, color, BOLD).next_to(box, UP, buff=0.08)
    return VGroup(box, text)


def _table_block(title, rows, color=KERNEL):
    box = RoundedRectangle(width=2.35, height=1.78, corner_radius=0.12, color=color, stroke_width=2)
    box.set_fill(PANEL_2, opacity=0.95)
    heading = t(title, 18, color, BOLD)
    row_items = VGroup(*[mono(row, 15, TEXT) for row in rows]).arrange(DOWN, buff=0.08)
    body = VGroup(heading, row_items).arrange(DOWN, buff=0.12).move_to(box)
    return VGroup(box, body)


def _ram_block():
    bars = VGroup()
    for index, color in enumerate([MUTED, SUCCESS, MUTED, KERNEL, MUTED]):
        bar = Rectangle(width=1.55, height=0.28, color=EDGE, stroke_width=1)
        bar.set_fill(color, opacity=0.42 if color == MUTED else 0.85)
        bars.add(bar)
    bars.arrange(DOWN, buff=0.06)
    label = t("RAM frames", 18, TEXT, BOLD).next_to(bars, UP, buff=0.12)
    return VGroup(label, bars)


def build_layout(layout_name, labels, summary_text):
    summary = t(summary_text, 27, TEXT, BOLD).to_edge(DOWN, buff=0.54)

    if layout_name == "privilege_boundary":
        user_zone = _zone("USER MODE", USER, UP * 1.35)
        kernel_zone = _zone("KERNEL MODE", KERNEL, DOWN * 1.15)
        boundary = DashedLine(LEFT * 5.9, RIGHT * 5.9, color=TEXT, stroke_width=2.5)
        primary = VGroup(
            _small_card("browser", USER, 1.65),
            _small_card("shell", USER, 1.45),
            _small_card("editor", USER, 1.55),
        ).arrange(RIGHT, buff=0.18).move_to(UP * 1.35 + LEFT * 1.1)
        secondary = card(_label(labels, 1, "controlled entry"), width=2.35, color=KERNEL, font_size=18).move_to(ORIGIN + RIGHT * 1.6)
        tertiary = card("kernel", width=2.0, color=KERNEL, font_size=22).move_to(DOWN * 1.15 + LEFT * 2.2)
        quaternary = VGroup(
            _small_card("memory", SUCCESS, 1.55),
            _small_card("drivers", HARDWARE, 1.55),
            _small_card("scheduler", PURPLE, 1.75),
        ).arrange(RIGHT, buff=0.18).move_to(DOWN * 1.15 + RIGHT * 2.25)
        path_a = Arrow(primary.get_bottom(), secondary.get_top(), buff=0.12, color=DANGER, stroke_width=3.5)
        path_b = Arrow(secondary.get_bottom(), tertiary.get_top(), buff=0.12, color=KERNEL, stroke_width=3.5)
        stage = VGroup(user_zone, kernel_zone, boundary)
        focus = secondary

    elif layout_name == "memory_translation":
        primary = code_card("0x7fff... virtual", width=2.65, color=USER).move_to(LEFT * 4.55 + UP * 0.45)
        secondary = card("MMU", width=1.8, color=PURPLE, font_size=24).move_to(LEFT * 1.75 + UP * 0.45)
        tertiary = _table_block("page table", ["vpn -> pfn", "flags: r/w", "valid: yes"], KERNEL).move_to(RIGHT * 1.15 + UP * 0.45)
        quaternary = _ram_block().move_to(RIGHT * 4.55 + UP * 0.45)
        caption = t(_label(labels, 0, "virtual address translation"), 20, TEXT).to_edge(UP, buff=1.16)
        path_a = connect(primary, secondary, USER)
        path_b = connect(secondary, quaternary, KERNEL)
        stage = VGroup(caption)
        focus = tertiary

    elif layout_name == "scheduler_timeline":
        timeline = Line(LEFT * 5.2 + DOWN * 0.95, RIGHT * 5.2 + DOWN * 0.95, color=EDGE, stroke_width=4)
        ticks = VGroup(*[Line(UP * 0.12, DOWN * 0.12, color=MUTED).move_to(LEFT * 4.6 + RIGHT * i * 1.15 + DOWN * 0.95) for i in range(9)])
        primary = VGroup(
            _small_card("task A", USER, 1.45),
            _small_card("task B", SUCCESS, 1.45),
            _small_card("task C", PURPLE, 1.45),
        ).arrange(RIGHT, buff=0.2).move_to(UP * 1.25 + LEFT * 2.3)
        secondary = card("CPU core", width=2.1, color=KERNEL, font_size=23).move_to(UP * 1.25 + RIGHT * 2.6)
        tertiary = Rectangle(width=1.8, height=0.34, color=KERNEL, stroke_width=2).set_fill(KERNEL, opacity=0.55).move_to(DOWN * 0.95 + LEFT * 2.45)
        quaternary = Rectangle(width=1.8, height=0.34, color=SUCCESS, stroke_width=2).set_fill(SUCCESS, opacity=0.55).move_to(DOWN * 0.95 + LEFT * 0.45)
        path_a = Arrow(primary.get_right(), secondary.get_left(), buff=0.14, color=KERNEL, stroke_width=3.5)
        path_b = Line(tertiary.get_right(), quaternary.get_left(), color=SUCCESS, stroke_width=4)
        stage = VGroup(timeline, ticks, t("time slices", 19, MUTED).next_to(timeline, DOWN, buff=0.16))
        focus = secondary

    elif layout_name == "cpu_registers":
        primary = _small_card("thread A", USER, 1.8).move_to(LEFT * 4.6 + UP * 0.75)
        secondary = _table_block("CPU registers", ["IP", "SP", "RAX", "RBX"], KERNEL).move_to(LEFT * 1.35 + UP * 0.75)
        tertiary = _table_block("saved state", ["A.ip", "A.sp", "A.regs"], USER).move_to(RIGHT * 1.45 + UP * 0.75)
        quaternary = _small_card("thread B", SUCCESS, 1.8).move_to(RIGHT * 4.65 + UP * 0.75)
        path_a = connect(primary, secondary, USER)
        path_b = connect(secondary, quaternary, SUCCESS)
        stage = VGroup(t(_label(labels, 0, "save state, restore state"), 22, TEXT).to_edge(UP, buff=1.15))
        focus = secondary

    elif layout_name == "hardware_path":
        primary = code_card("user request", width=2.35, color=USER).move_to(LEFT * 4.55 + UP * 0.55)
        secondary = card("kernel validation", width=2.65, color=KERNEL, font_size=19).move_to(LEFT * 1.55 + UP * 0.55)
        tertiary = card("driver", width=2.0, color=PURPLE, font_size=22).move_to(RIGHT * 1.55 + UP * 0.55)
        quaternary = VGroup(
            _small_card("disk", HARDWARE, 1.35),
            _small_card("network", SUCCESS, 1.65),
        ).arrange(DOWN, buff=0.16).move_to(RIGHT * 4.65 + UP * 0.55)
        path_a = connect(primary, secondary, USER)
        path_b = connect(secondary, quaternary, KERNEL)
        stage = VGroup(t("mediated I/O path", 22, TEXT).to_edge(UP, buff=1.16))
        focus = secondary

    elif layout_name == "syscall_gate":
        primary = code_card("write(fd, buf)", width=2.55, color=USER).move_to(LEFT * 4.4 + UP * 0.4)
        secondary = card("syscall gate", width=2.35, color=KERNEL, font_size=22).move_to(LEFT * 1.25 + UP * 0.4)
        tertiary = _table_block("arguments", ["rax: number", "rdi: fd", "rsi: buf"], PURPLE).move_to(RIGHT * 1.55 + UP * 0.4)
        quaternary = card("kernel handler", width=2.45, color=SUCCESS, font_size=20).move_to(RIGHT * 4.55 + UP * 0.4)
        blocked = DashedLine(primary.get_bottom(), quaternary.get_bottom(), color=DANGER, stroke_width=3).shift(DOWN * 1.0)
        cross = VGroup(
            Line(LEFT * 0.18 + DOWN * 0.18, RIGHT * 0.18 + UP * 0.18, color=DANGER, stroke_width=5),
            Line(LEFT * 0.18 + UP * 0.18, RIGHT * 0.18 + DOWN * 0.18, color=DANGER, stroke_width=5),
        ).move_to(blocked)
        path_a = connect(primary, secondary, USER)
        path_b = connect(secondary, quaternary, KERNEL)
        stage = VGroup(blocked, cross, t("direct jump blocked", 18, DANGER, BOLD).next_to(blocked, DOWN, buff=0.12))
        focus = secondary

    elif layout_name == "recap_map":
        primary = card("programs ask", width=2.45, color=USER, font_size=22).move_to(LEFT * 3.8 + UP * 0.55)
        secondary = card("kernel decides", width=2.55, color=KERNEL, font_size=22).move_to(ORIGIN + UP * 0.55)
        tertiary = card("hardware acts", width=2.45, color=SUCCESS, font_size=22).move_to(RIGHT * 3.8 + UP * 0.55)
        quaternary = VGroup(
            _small_card("syscalls", USER, 1.65),
            _small_card("memory", SUCCESS, 1.55),
            _small_card("scheduler", PURPLE, 1.85),
            _small_card("drivers", HARDWARE, 1.55),
        ).arrange(RIGHT, buff=0.18).move_to(DOWN * 1.35)
        path_a = connect(primary, secondary, USER)
        path_b = connect(secondary, tertiary, KERNEL)
        stage = VGroup(t("one recurring kernel pattern", 22, TEXT).to_edge(UP, buff=1.16))
        focus = secondary

    else:
        primary = code_card(_label(labels, 0, "user action"), width=3.0, color=USER).move_to(LEFT * 4.05 + UP * 0.55)
        secondary = card(_label(labels, 1, "kernel decision"), width=3.0, color=KERNEL).move_to(ORIGIN + UP * 0.55)
        tertiary = card(_label(labels, 2, "resource access"), width=3.0, color=SUCCESS).move_to(RIGHT * 4.05 + UP * 0.55)
        quaternary = card(_label(labels, 3, "result returns"), width=4.15, height=0.82, color=PURPLE, font_size=19).move_to(DOWN * 1.45)
        path_a = connect(primary, secondary, USER)
        path_b = connect(secondary, tertiary, KERNEL)
        stage = VGroup(t(_label(labels, 4, "controlled path"), 22, TEXT).to_edge(UP, buff=1.16))
        focus = secondary

    moving = flow_dot(path_a, KERNEL)
    all_items = VGroup(stage, primary, secondary, tertiary, quaternary, path_a, path_b, moving, summary)
    return {{
        "stage": stage,
        "primary": primary,
        "secondary": secondary,
        "tertiary": tertiary,
        "quaternary": quaternary,
        "path_a": path_a,
        "path_b": path_b,
        "moving": moving,
        "focus": focus,
        "summary": summary,
        "all": all_items,
    }}


class EnglishGeneratedScene(Scene):
    scene_key = ""
    fallback_duration = 35.0

    def setup(self):
        self.camera.background_color = BG

    def now(self):
        return self.renderer.time

    def begin_sync(self):
        self._sync_start = self.now()
        self._scene_duration = duration(self.scene_key, self.fallback_duration)
        text = SEGMENT_TEXT.get(self.scene_key)
        if text:
            self.add_subcaption(text, duration=self._scene_duration)

    def scene_duration(self):
        return getattr(self, "_scene_duration", duration(self.scene_key, self.fallback_duration))

    def cue(self, ratio):
        return self._sync_start + self.scene_duration() * ratio

    def hold_until(self, ratio):
        self.wait(max(0, self.cue(ratio) - self.now()))

    def play_until(self, ratio, *animations, min_run_time=0.25, rate_func=smooth):
        run_time = max(min_run_time, self.cue(ratio) - self.now())
        self.play(*animations, run_time=run_time, rate_func=rate_func)

    def finish_sync(self, trailing_animation=0.7):
        target = self.scene_duration()
        elapsed = self.now() - self._sync_start
        self.wait(max(0, target - elapsed - trailing_animation))
{scenes}
'''


def _render_script(blueprint: VideoBlueprint, slug_module: str) -> str:
    scene_lines = "\n".join(f"  {scene.key}" for scene in blueprint.scenes)
    concat_lines = "\n".join(
        f"file 'media/videos/{slug_module}_en/${{QUALITY_DIR}}/{scene.key}.mp4'"
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
        style_text = style_src.read_text(encoding="utf-8")
        style_text = style_text.replace('FONT = "Helvetica Neue"', 'FONT = "DejaVu Sans"')
        style_text = style_text.replace('MONO = "Menlo"', 'MONO = "DejaVu Sans Mono"')
        (video_dir / f"{slug_module}_style.py").write_text(style_text, encoding="utf-8")

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
