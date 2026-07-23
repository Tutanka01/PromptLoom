from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path

from video_api.config import Settings
from video_api.pipeline.voice import prune_stale_audio, voice_signature
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
    # Beat-driven scene: one card per beat, revealed at the beat's own ratio so the
    # on-screen keyword appears exactly when the narration says it. All geometry,
    # timing and focus handling lives in the deterministic base class (run_beat_scene).
    beats = [
        {"at": round(beat.at, 3), "label": beat.label or _short(beat.text_hint, 40)}
        for beat in scene.beats
    ]
    return f'''

class {scene.key}(EnglishGeneratedScene):
    scene_key = {_py(scene.key)}
    fallback_duration = {scene.duration_seconds}
    layout_name = {_py(scene.layout)}
    title_text = {_py(scene.title)}
    beats = {json.dumps(beats, ensure_ascii=True)}

    def construct(self):
        self.run_beat_scene()
'''


# The generated Manim module. Kept as a plain (non-f) string so the embedded Python
# (dicts, sets, format-free literals) needs no brace escaping. __SLUG_MODULE__ is the
# only placeholder; scene classes are appended after it.
_MODULE_TEMPLATE = '''import json
import math
from pathlib import Path

from manim import *

from __SLUG_MODULE___style import (
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
    data = load_json(SEGMENTS_FILE, {"segments": []})
    return {segment["key"]: segment["text"] for segment in data["segments"]}


DURATIONS = load_json(DURATIONS_FILE, {})
SEGMENT_TEXT = load_segments()


def duration(key, fallback):
    return float(DURATIONS.get(key, fallback))


def fade_group(*items):
    return VGroup(*[item for item in items if item is not None])


# ---------------------------------------------------------------------------
# Beat-driven visual grammar
# ---------------------------------------------------------------------------

PALETTE = [USER, KERNEL, SUCCESS, PURPLE, HARDWARE, USER, KERNEL, SUCCESS]

FAMILY = {
    "concept_map": "radial",
    "recap_map": "radial",
    "process_flow": "flow",
    "equation_transform": "flow",
    "layered_system": "stack",
    "timeline": "timeline",
    "cycle_diagram": "cycle",
    "graph_plot": "graph",
    "spatial_model": "graph",
    "comparison_table": "columns",
}


def beat_card(label, color):
    inner_w = 3.6
    text = t(label, 22, TEXT)
    if text.width > inner_w:
        text.scale(inner_w / text.width)
    box = RoundedRectangle(
        width=max(1.9, text.width + 0.6),
        height=0.92,
        corner_radius=0.16,
        stroke_color=color,
        stroke_width=2.5,
        fill_color=PANEL,
        fill_opacity=0.97,
    )
    text.move_to(box)
    accent = Line(
        box.get_corner(DL) + RIGHT * 0.18,
        box.get_corner(DR) + LEFT * 0.18,
        color=color,
        stroke_width=3.5,
    )
    return VGroup(box, accent, text)


def focus_ring(mob):
    return SurroundingRectangle(mob, color=KERNEL, buff=0.14, corner_radius=0.18, stroke_width=3.5)


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


def _fit(group, max_w=12.8, max_h=5.6):
    if group.width > max_w:
        group.scale(max_w / group.width)
    if group.height > max_h:
        group.scale(max_h / group.height)
    return group


def _place_radial(cards):
    center = cards[0]
    sats = cards[1:]
    center.move_to(DOWN * 0.35)
    count = max(1, len(sats))
    for index, satellite in enumerate(sats):
        angle = PI / 2 - TAU * index / count
        satellite.move_to(
            center.get_center() + RIGHT * (math.cos(angle) * 4.6) + UP * (math.sin(angle) * 2.4)
        )
    _fit(VGroup(*cards))
    links = [None]
    for satellite in sats:
        links.append(Line(center.get_center(), satellite.get_center(), color=EDGE, stroke_width=2))
    return VGroup(), links


def _place_flow(cards):
    count = len(cards)
    if count <= 4:
        group = VGroup(*cards).arrange(RIGHT, buff=0.6)
    else:
        group = VGroup(*cards).arrange_in_grid(rows=2, buff=(0.6, 0.85))
    group.move_to(DOWN * 0.35)
    _fit(group)
    links = [None]
    for index in range(1, count):
        left, right = cards[index - 1], cards[index]
        if abs(left.get_center()[1] - right.get_center()[1]) < 0.35:
            links.append(
                Arrow(
                    left.get_right(),
                    right.get_left(),
                    buff=0.12,
                    color=MUTED,
                    stroke_width=3.5,
                    max_tip_length_to_length_ratio=0.18,
                )
            )
        else:
            links.append(None)
    return VGroup(), links


def _place_stack(cards):
    count = len(cards)
    group = VGroup(*cards).arrange(DOWN, buff=0.5).move_to(DOWN * 0.35)
    _fit(group, max_h=6.0)
    links = [None]
    for index in range(1, count):
        links.append(
            Arrow(
                cards[index - 1].get_bottom(),
                cards[index].get_top(),
                buff=0.06,
                color=MUTED,
                stroke_width=4,
                max_tip_length_to_length_ratio=0.4,
            )
        )
    return VGroup(), links


def _place_columns(cards):
    group = VGroup(*cards).arrange_in_grid(cols=2, buff=(0.8, 0.45)).move_to(DOWN * 0.35)
    _fit(group)
    return VGroup(), [None] * len(cards)


def _place_timeline(cards):
    count = len(cards)
    axis_y = -0.4
    xs = [-5.4 + 10.8 * index / max(1, count - 1) for index in range(count)]
    for index, c in enumerate(cards):
        c.move_to(RIGHT * xs[index] + UP * (1.55 if index % 2 == 0 else -2.35))
    _fit(VGroup(*cards))
    axis = Line(LEFT * 6 + UP * axis_y, RIGHT * 6 + UP * axis_y, color=EDGE, stroke_width=4)
    links = []
    for c in cards:
        foot = RIGHT * c.get_center()[0] + UP * axis_y
        links.append(Line(c.get_center(), foot, color=EDGE, stroke_width=2))
    return VGroup(axis), links


def _place_cycle(cards):
    count = len(cards)
    for index, c in enumerate(cards):
        angle = PI / 2 - TAU * index / count
        c.move_to(DOWN * 0.35 + RIGHT * (math.cos(angle) * 4.4) + UP * (math.sin(angle) * 2.4))
    _fit(VGroup(*cards))
    links = [None]
    for index in range(1, count):
        links.append(
            ArcBetweenPoints(
                cards[index - 1].get_center(),
                cards[index].get_center(),
                angle=-TAU / 10,
                color=EDGE,
                stroke_width=2.5,
            )
        )
    closing = ArcBetweenPoints(
        cards[-1].get_center(), cards[0].get_center(), angle=-TAU / 10, color=EDGE, stroke_width=2.5
    )
    return VGroup(closing), links


def _place_graph(cards):
    axes = _simple_axes().scale(1.2).move_to(LEFT * 3.5 + DOWN * 0.2)
    group = VGroup(*cards).arrange(DOWN, buff=0.32).move_to(RIGHT * 3.4 + DOWN * 0.3)
    _fit(group, max_w=6.4, max_h=5.2)
    return VGroup(axes), [None] * len(cards)


_PLACERS = {
    "radial": _place_radial,
    "flow": _place_flow,
    "stack": _place_stack,
    "timeline": _place_timeline,
    "cycle": _place_cycle,
    "graph": _place_graph,
    "columns": _place_columns,
}


def build_scene(layout_name, labels):
    cards = [beat_card(label, PALETTE[index % len(PALETTE)]) for index, label in enumerate(labels)]
    family = FAMILY.get(layout_name, "flow")
    backdrop, links = _PLACERS[family](cards)
    all_items = VGroup(backdrop, *[link for link in links if link is not None], *cards)
    return {"backdrop": backdrop, "items": cards, "links": links, "all": all_items}


class EnglishGeneratedScene(Scene):
    scene_key = ""
    fallback_duration = 35.0
    layout_name = "concept_map"
    title_text = ""
    beats = []

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

    def run_beat_scene(self):
        self.begin_sync()
        bg = make_background()
        title = title_bar(self.title_text)
        scene = build_scene(self.layout_name, [beat["label"] for beat in self.beats])
        items, links = scene["items"], scene["links"]

        self.add(bg)
        first_at = self.beats[0]["at"] if self.beats else 0.1
        intro = [FadeIn(title)]
        if len(scene["backdrop"]) > 0:
            intro.append(FadeIn(scene["backdrop"]))
        self.play_until(max(0.04, min(first_at * 0.6, 0.10)), *intro)

        focus = None
        for index, (item, beat) in enumerate(zip(items, self.beats)):
            anims = [FadeIn(item, shift=UP * 0.12)]
            if links[index] is not None:
                anims.append(Create(links[index]))
            if focus is None:
                focus = focus_ring(item)
                anims.append(FadeIn(focus))
            else:
                anims.append(Transform(focus, focus_ring(item)))
            self.play_until(beat["at"], *anims)

        self.finish_sync()
        closing = fade_group(scene["all"], title, bg, focus)
        self.play(FadeOut(closing), run_time=0.6)
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
    header = _MODULE_TEMPLATE.replace("__SLUG_MODULE__", slug_module)
    return header + scenes + "\n"


def build_single_scene_module(slug_module: str, scene_class_code: str) -> str:
    """Build a complete, importable Manim module containing only one scene class.

    Used to validate / smoke-render a single candidate scene in isolation before it
    is trusted and written into the full module. The header carries the same imports,
    helpers and base class as the real module, so the scene renders identically.
    """
    header = _MODULE_TEMPLATE.replace("__SLUG_MODULE__", slug_module)
    return header + scene_class_code + "\n"


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
AUDIO="${{AUDIO:-audio/en/voiceover_en.wav}}"
OUTPUT="${{OUTPUT:-final/{blueprint.slug}-en-final.mp4}}"
VOICE_INPUT="${{AUDIO}}"

# Voice mastering: a broadcast-style chain applied to the concatenated voiceover
# at mux time (never to the cached per-segment WAVs, so segment caches stay
# byte-identical and reusable):
#   highpass     removes rumble/DC below the voice fundamentals (~80 Hz);
#   deesser      tames TTS sibilance ("s"/"sh" harshness at speech peaks);
#   acompressor  gentle 2.5:1 levelling so quiet syllables stay intelligible
#                without pumping (threshold 0.06 linear ~ -24 dBFS).
# No makeup gain here: the loudnorm stage below owns the final level. The chain
# is included in the loudnorm measure pass so the measurement matches the graph
# that ships. VOICE_MASTERING_ENABLED=0 keeps the raw voice; VOICE_MASTER_CHAIN
# overrides the whole filter chain for tuning.
VOICE_MASTERING_ENABLED="${{VOICE_MASTERING_ENABLED:-1}}"
VOICE_MASTER_CHAIN="${{VOICE_MASTER_CHAIN:-highpass=f=80,deesser=i=0.4,acompressor=threshold=0.06:ratio=2.5:attack=9:release=200}}"
MASTER_PREFIX=""
if [[ "${{VOICE_MASTERING_ENABLED}}" == "1" ]]; then
  MASTER_PREFIX="${{VOICE_MASTER_CHAIN}},"
fi

# Loudness normalisation (EBU R128, two-pass loudnorm). A first "measure" pass
# analyses the exact audio graph that will ship and reports its integrated
# loudness / true-peak / LRA; the apply pass then feeds those measurements back
# into loudnorm with linear=true, which applies a single linear gain toward the
# target instead of the dynamic compression a blind one-pass run does. This is
# measurably more accurate and free of the pumping artefacts of single-pass. If
# the measure pass or its JSON parsing fails for any reason (non-zero exit,
# missing keys, non-finite "-inf" values), the script falls back to the original
# single-pass filter and prints a note. LOUDNESS_TARGET is integrated loudness in
# LUFS (default -14, the YouTube/streaming norm), LOUDNESS_TP the true-peak
# ceiling in dBTP. Set LOUDNORM_ENABLED=0 to fall back to the raw (unnormalised)
# mux.
LOUDNORM_ENABLED="${{LOUDNORM_ENABLED:-1}}"
LOUDNESS_TARGET="${{LOUDNESS_TARGET:--14}}"
LOUDNESS_TP="${{LOUDNESS_TP:--1.5}}"
LOUDNESS_LRA="${{LOUDNESS_LRA:-11}}"
# Single-pass filter: the automatic fallback whenever a measure pass fails.
LOUDNORM_SINGLE="loudnorm=I=${{LOUDNESS_TARGET}}:TP=${{LOUDNESS_TP}}:LRA=${{LOUDNESS_LRA}}"

# parse_loudnorm turns a loudnorm print_format=json report ($1 = captured ffmpeg
# stderr) into the second-pass "loudnorm=...:measured_*:...:linear=true" filter.
# It exits non-zero when a required key is missing or a value is non-finite
# (loudnorm prints "-inf" for silence, which float() parses as -inf), so the
# caller can fall back to single-pass. jq is not guaranteed in the worker image;
# python3 is (build_video_json.py already relies on it).
parse_loudnorm() {{
  python3 -c 'import sys
raw = sys.argv[1]
target, tp, lra = sys.argv[2], sys.argv[3], sys.argv[4]
wanted = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
q = chr(34)
vals = dict()
for line in raw.splitlines():
    if ":" not in line:
        continue
    left, _sep, right = line.partition(":")
    key = left.replace(q, "").replace(",", "").strip()
    if key not in wanted:
        continue
    v = right.replace(q, "").replace(",", "").strip()
    try:
        f = float(v)
    except ValueError:
        continue
    if f != f or f == float("inf") or f == float("-inf"):
        continue
    vals[key] = v
if len(vals) != len(wanted):
    sys.exit(1)
sys.stdout.write("loudnorm=I=" + target + ":TP=" + tp + ":LRA=" + lra + ":measured_I=" + vals["input_i"] + ":measured_TP=" + vals["input_tp"] + ":measured_LRA=" + vals["input_lra"] + ":measured_thresh=" + vals["input_thresh"] + ":offset=" + vals["target_offset"] + ":linear=true")
' "$1" "${{LOUDNESS_TARGET}}" "${{LOUDNESS_TP}}" "${{LOUDNESS_LRA}}"
}}

# apad extends the voice stream with silence to cover the full video duration.
# -shortest then trims everything to the video end. This prevents the audio
# track from ending before the video (which caused freezedetect
# false-positives on the silent last seconds).
VOICE_CHAIN="${{MASTER_PREFIX}}apad"
if [[ "${{LOUDNORM_ENABLED}}" == "1" ]]; then
  # Measure the MASTERED voice without apad: loudnorm's gating excludes the
  # trailing silence, so padding does not change the integrated loudness we
  # measure — but the mastering chain does, hence it precedes the measure.
  if MEASURED_JSON=$(ffmpeg -nostdin -hide_banner -i "${{VOICE_INPUT}}" -af "${{MASTER_PREFIX}}${{LOUDNORM_SINGLE}}:print_format=json" -f null - 2>&1 >/dev/null) \\
     && MEASURED=$(parse_loudnorm "${{MEASURED_JSON}}"); then
    VOICE_CHAIN="${{MASTER_PREFIX}}${{MEASURED}},apad"
  else
    echo "loudnorm: two-pass measure failed for the voiceover; using single-pass."
    VOICE_CHAIN="${{MASTER_PREFIX}}${{LOUDNORM_SINGLE}},apad"
  fi
fi
ffmpeg -y \\
  -i "${{VIDEO}}" \\
  -i "${{VOICE_INPUT}}" \\
  -filter_complex "[1:a]${{VOICE_CHAIN}}[a_padded]" \\
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
        for generated_name in ["media", "final", "renders"]:
            generated_path = video_dir / generated_name
            if generated_path.exists():
                shutil.rmtree(generated_path)
        for concat_path in video_dir.glob("concat*.txt"):
            concat_path.unlink()
        # audio/ is NOT wiped: per-segment WAVs are cached by text+voice-params hash
        # so a repair attempt only re-synthesizes the segments that actually changed.
        prune_stale_audio(
            video_dir,
            _segments_json(blueprint)["segments"],
            voice_signature(self.settings),
        )

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
        style_text = style_text.replace('FONT = "Helvetica Neue"', 'FONT = "Inter"')
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
