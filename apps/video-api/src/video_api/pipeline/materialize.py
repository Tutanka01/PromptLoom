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
    objectives = "\n".join(f"- {objective}" for objective in blueprint.learning_objectives)
    return f"""# {blueprint.title}

## Topic

{blueprint.teaching_goal}

## Subject

Area: {blueprint.subject_area}

Difficulty: {blueprint.difficulty}

## Audience

{blueprint.audience}

## Learning Objectives

{objectives}

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
    # On-screen cards must show readable phrases tied to the narration (beat.label),
    # never the renderer instruction (visual_action). Cycle the available labels so
    # short scenes still fill all five card slots with on-topic text.
    labels = [beat.label for beat in scene.beats if beat.label] or [scene.title]
    beat_cards = [labels[index % len(labels)] for index in range(5)]
    summary = _short(scene.beats[-1].text_hint, 58)
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


def _manim_code(
    blueprint: VideoBlueprint,
    slug_module: str,
    custom_scene_codes: dict[str, str] | None = None,
) -> str:
    parts = []
    for scene in blueprint.scenes:
        if custom_scene_codes and scene.key in custom_scene_codes:
            parts.append(custom_scene_codes[scene.key])
        else:
            parts.append(_scene_code(scene))
    scenes = "\n".join(parts)
    return f'''import json
from pathlib import Path

from manim import *

from {slug_module}_style import (
    BG,
    BODY,
    CAP,
    CODE,
    DANGER,
    EDGE,
    H1,
    H2,
    HARDWARE,
    KERNEL,
    MUTED,
    PANEL,
    PANEL_2,
    PURPLE,
    SUCCESS,
    TEXT,
    USER,
    card,
    code_card,
    connect,
    dim,
    flow_dot,
    glow,
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


def _layer(label, color, center, width=5.6):
    box = RoundedRectangle(width=width, height=1.18, corner_radius=0.14, color=color, stroke_width=2)
    box.set_fill(PANEL_2, opacity=0.52).move_to(center)
    text = t(label, 18, color, BOLD).move_to(box)
    return VGroup(box, text)


def _table_block(title, rows, color=KERNEL, width=3.2):
    box = RoundedRectangle(width=width, height=1.86, corner_radius=0.12, color=color, stroke_width=2)
    box.set_fill(PANEL_2, opacity=0.95)
    heading = t(title, 18, color, BOLD)
    row_items = VGroup(*[t(row, 15, TEXT) for row in rows]).arrange(DOWN, buff=0.08)
    body = VGroup(heading, row_items).arrange(DOWN, buff=0.12).move_to(box)
    return VGroup(box, body)


def _simple_axes():
    x_axis = Line(LEFT * 2.45, RIGHT * 2.45, color=EDGE, stroke_width=3)
    y_axis = Line(DOWN * 1.35, UP * 1.35, color=EDGE, stroke_width=3).move_to(x_axis.get_left())
    curve = VMobject(color=SUCCESS, stroke_width=4)
    curve.set_points_smoothly([
        LEFT * 2.2 + DOWN * 0.95,
        LEFT * 1.1 + DOWN * 0.15,
        ORIGIN + UP * 0.55,
        RIGHT * 1.2 + UP * 0.15,
        RIGHT * 2.25 + UP * 0.95,
    ])
    curve.move_to(ORIGIN)
    return VGroup(x_axis, y_axis, curve)


def build_layout(layout_name, labels, summary_text):
    summary = t(summary_text, 27, TEXT, BOLD).to_edge(DOWN, buff=0.54)

    if layout_name == "concept_map":
        primary = card(_label(labels, 0, "core idea"), width=3.0, color=KERNEL, font_size=22).move_to(ORIGIN + UP * 0.55)
        secondary = card(_label(labels, 1, "first cue"), width=2.4, color=USER, font_size=18).move_to(LEFT * 4.0 + UP * 1.35)
        tertiary = card(_label(labels, 2, "second cue"), width=2.4, color=SUCCESS, font_size=18).move_to(RIGHT * 4.0 + UP * 1.35)
        quaternary = VGroup(
            _small_card(_label(labels, 3, "example"), PURPLE, 1.9),
            _small_card(_label(labels, 4, "transfer"), HARDWARE, 1.9),
        ).arrange(RIGHT, buff=0.22).move_to(DOWN * 1.15)
        path_a = Arrow(secondary.get_right(), primary.get_left(), buff=0.14, color=USER, stroke_width=3.5)
        path_b = Arrow(primary.get_right(), tertiary.get_left(), buff=0.14, color=SUCCESS, stroke_width=3.5)
        stage = VGroup(Line(primary.get_bottom(), quaternary.get_top(), color=EDGE, stroke_width=3))
        focus = primary

    elif layout_name == "layered_system":
        layer_a = _layer(_label(labels, 0, "surface observation"), USER, UP * 1.45)
        layer_b = _layer(_label(labels, 1, "hidden mechanism"), KERNEL, ORIGIN)
        layer_c = _layer(_label(labels, 2, "measurable result"), SUCCESS, DOWN * 1.45)
        primary = layer_a
        secondary = layer_b
        tertiary = layer_c
        quaternary = card(_label(labels, 3, "why it matters"), width=3.2, height=0.76, color=PURPLE, font_size=18).to_edge(RIGHT, buff=0.74).shift(DOWN * 0.05)
        path_a = Arrow(primary.get_bottom(), secondary.get_top(), buff=0.12, color=KERNEL, stroke_width=3.5)
        path_b = Arrow(secondary.get_bottom(), tertiary.get_top(), buff=0.12, color=SUCCESS, stroke_width=3.5)
        stage = VGroup(t(_label(labels, 4, "layered explanation"), 22, TEXT).to_edge(UP, buff=1.16))
        focus = secondary

    elif layout_name == "timeline":
        timeline = Line(LEFT * 5.2 + DOWN * 0.92, RIGHT * 5.2 + DOWN * 0.92, color=EDGE, stroke_width=4)
        ticks = VGroup(*[Line(UP * 0.12, DOWN * 0.12, color=MUTED).move_to(LEFT * 4.6 + RIGHT * i * 1.15 + DOWN * 0.92) for i in range(9)])
        primary = card(_label(labels, 0, "start"), width=2.15, color=USER, font_size=19).move_to(LEFT * 4.15 + UP * 0.75)
        secondary = card(_label(labels, 1, "change"), width=2.15, color=KERNEL, font_size=19).move_to(LEFT * 1.35 + UP * 0.75)
        tertiary = card(_label(labels, 2, "transition"), width=2.15, color=PURPLE, font_size=19).move_to(RIGHT * 1.35 + UP * 0.75)
        quaternary = card(_label(labels, 3, "result"), width=2.15, color=SUCCESS, font_size=19).move_to(RIGHT * 4.15 + UP * 0.75)
        path_a = connect(primary, secondary, USER)
        path_b = connect(secondary, quaternary, KERNEL)
        stage = VGroup(timeline, ticks, t(_label(labels, 4, "sequence over time"), 19, MUTED).next_to(timeline, DOWN, buff=0.16))
        focus = secondary

    elif layout_name == "equation_transform":
        primary = code_card(_label(labels, 0, "starting expression"), width=3.1, color=USER, font_size=19).move_to(LEFT * 4.1 + UP * 0.55)
        secondary = code_card(_label(labels, 1, "rewrite"), width=2.7, color=KERNEL, font_size=19).move_to(LEFT * 1.25 + UP * 0.55)
        tertiary = code_card(_label(labels, 2, "operation"), width=2.7, color=PURPLE, font_size=19).move_to(RIGHT * 1.55 + UP * 0.55)
        quaternary = code_card(_label(labels, 3, "meaning"), width=2.9, color=SUCCESS, font_size=19).move_to(RIGHT * 4.55 + UP * 0.55)
        path_a = connect(primary, secondary, USER)
        path_b = connect(secondary, quaternary, KERNEL)
        stage = VGroup(t(_label(labels, 4, "notation follows the idea"), 22, TEXT).to_edge(UP, buff=1.16))
        focus = tertiary

    elif layout_name == "graph_plot":
        graph = _simple_axes().scale(1.2).move_to(LEFT * 2.15 + UP * 0.45)
        primary = graph
        secondary = Line(LEFT * 1.1, RIGHT * 1.1, color=KERNEL, stroke_width=4).rotate(0.42).move_to(LEFT * 2.15 + UP * 0.70)
        tertiary = card(_label(labels, 1, "positive slope"), width=2.4, color=SUCCESS, font_size=18).move_to(RIGHT * 3.25 + UP * 1.15)
        quaternary = card(_label(labels, 2, "negative or flat"), width=2.7, color=PURPLE, font_size=18).move_to(RIGHT * 3.25 + DOWN * 0.35)
        path_a = Arrow(secondary.get_right(), tertiary.get_left(), buff=0.12, color=SUCCESS, stroke_width=3.5)
        path_b = Arrow(secondary.get_right(), quaternary.get_left(), buff=0.12, color=PURPLE, stroke_width=3.5)
        stage = VGroup(t(_label(labels, 4, "read the curve locally"), 22, TEXT).to_edge(UP, buff=1.16))
        focus = secondary

    elif layout_name == "comparison_table":
        primary = _table_block(_label(labels, 0, "case"), [_label(labels, 1, "example"), _label(labels, 2, "units"), _label(labels, 3, "meaning")], USER, width=3.25).move_to(LEFT * 3.55 + UP * 0.5)
        secondary = _table_block("compare", ["before", "after", "interpret"], KERNEL, width=2.7).move_to(ORIGIN + UP * 0.5)
        tertiary = _table_block(_label(labels, 4, "takeaway"), ["same structure", "different labels", "clear meaning"], SUCCESS, width=3.15).move_to(RIGHT * 3.55 + UP * 0.5)
        quaternary = card("match form to meaning", width=3.6, color=PURPLE, font_size=20).move_to(DOWN * 1.45)
        path_a = connect(primary, secondary, USER)
        path_b = connect(secondary, tertiary, KERNEL)
        stage = VGroup(t("structured comparison", 22, TEXT).to_edge(UP, buff=1.16))
        focus = secondary

    elif layout_name == "cycle_diagram":
        primary = card(_label(labels, 0, "condition"), width=2.25, color=USER, font_size=18).move_to(UP * 1.55)
        secondary = card(_label(labels, 1, "case A"), width=2.25, color=KERNEL, font_size=18).move_to(RIGHT * 3.25 + UP * 0.2)
        tertiary = card(_label(labels, 2, "case B"), width=2.25, color=PURPLE, font_size=18).move_to(DOWN * 1.55)
        quaternary = card(_label(labels, 3, "case C"), width=2.25, color=SUCCESS, font_size=18).move_to(LEFT * 3.25 + UP * 0.2)
        path_a = ArcBetweenPoints(primary.get_right(), secondary.get_top(), angle=-TAU / 6, color=KERNEL, stroke_width=3.5)
        path_b = ArcBetweenPoints(secondary.get_bottom(), tertiary.get_right(), angle=-TAU / 6, color=SUCCESS, stroke_width=3.5)
        stage = VGroup(
            ArcBetweenPoints(tertiary.get_left(), quaternary.get_bottom(), angle=-TAU / 6, color=PURPLE, stroke_width=3),
            ArcBetweenPoints(quaternary.get_top(), primary.get_left(), angle=-TAU / 6, color=USER, stroke_width=3),
            t(_label(labels, 4, "cycle through cases"), 22, TEXT).to_edge(UP, buff=1.16),
        )
        focus = primary

    elif layout_name == "spatial_model":
        primary = _simple_axes().move_to(LEFT * 3.55 + UP * 0.45)
        point_a = Dot(LEFT * 3.85 + UP * 0.45, color=USER)
        point_b = Dot(LEFT * 2.55 + UP * 0.82, color=SUCCESS)
        primary.add(point_a, point_b)
        secondary = card(_label(labels, 1, "movement"), width=2.45, color=KERNEL, font_size=18).move_to(ORIGIN + UP * 0.55)
        tertiary = card(_label(labels, 2, "local view"), width=2.45, color=PURPLE, font_size=18).move_to(RIGHT * 3.3 + UP * 0.95)
        quaternary = card(_label(labels, 3, "result"), width=2.45, color=SUCCESS, font_size=18).move_to(RIGHT * 3.3 + DOWN * 0.65)
        path_a = Arrow(point_b.get_center(), secondary.get_left(), buff=0.12, color=KERNEL, stroke_width=3.5)
        path_b = Arrow(secondary.get_right(), tertiary.get_left(), buff=0.12, color=SUCCESS, stroke_width=3.5)
        stage = VGroup(t(_label(labels, 4, "spatial relationship"), 22, TEXT).to_edge(UP, buff=1.16))
        focus = secondary

    elif layout_name == "recap_map":
        primary = card(_label(labels, 0, "idea"), width=2.45, color=USER, font_size=21).move_to(LEFT * 3.8 + UP * 0.55)
        secondary = card(_label(labels, 1, "mechanism"), width=2.55, color=KERNEL, font_size=21).move_to(ORIGIN + UP * 0.55)
        tertiary = card(_label(labels, 2, "result"), width=2.45, color=SUCCESS, font_size=21).move_to(RIGHT * 3.8 + UP * 0.55)
        quaternary = VGroup(
            _small_card(_label(labels, 3, "application"), PURPLE, 1.85),
            _small_card(_label(labels, 4, "takeaway"), HARDWARE, 1.85),
        ).arrange(RIGHT, buff=0.18).move_to(DOWN * 1.35)
        path_a = connect(primary, secondary, USER)
        path_b = connect(secondary, tertiary, KERNEL)
        stage = VGroup(t("recap map", 22, TEXT).to_edge(UP, buff=1.16))
        focus = secondary

    else:
        primary = code_card(_label(labels, 0, "starting idea"), width=3.0, color=USER).move_to(LEFT * 4.05 + UP * 0.55)
        secondary = card(_label(labels, 1, "mechanism"), width=3.0, color=KERNEL).move_to(ORIGIN + UP * 0.55)
        tertiary = card(_label(labels, 2, "result"), width=3.0, color=SUCCESS).move_to(RIGHT * 4.05 + UP * 0.55)
        quaternary = card(_label(labels, 3, "interpretation"), width=4.15, height=0.82, color=PURPLE, font_size=19).move_to(DOWN * 1.45)
        path_a = connect(primary, secondary, USER)
        path_b = connect(secondary, tertiary, KERNEL)
        stage = VGroup(t(_label(labels, 4, "explanation path"), 22, TEXT).to_edge(UP, buff=1.16))
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

# apad extends the audio stream with silence to cover the full video duration.
# -shortest then trims any remaining audio tail beyond the video end.
# This prevents the audio track from ending before the video (which caused
# freezedetect false-positives on the silent last seconds).
ffmpeg -y \\
  -i "${{VIDEO}}" \\
  -i "${{AUDIO}}" \\
  -filter_complex "[1:a]apad[a_padded]" \\
  -map 0:v:0 \\
  -map "[a_padded]" \\
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

    def write_scene_codes(
        self,
        video_dir: Path,
        blueprint: VideoBlueprint,
        scene_codes: dict[str, str],
    ) -> None:
        """Rewrite the Manim file with LLM-generated scene code.

        Scenes not present in scene_codes keep the deterministic fallback template.
        """
        slug_module = blueprint.slug.replace("-", "_")
        manim_path = video_dir / f"{slug_module}_en.py"
        manim_path.write_text(
            _manim_code(blueprint, slug_module, scene_codes),
            encoding="utf-8",
        )
        llm_count = len(scene_codes)
        fallback_count = len(blueprint.scenes) - llm_count
        logger.info(
            "materialize.scene_codes_written video_dir=%s llm_scenes=%d fallback_scenes=%d",
            video_dir,
            llm_count,
            fallback_count,
        )
