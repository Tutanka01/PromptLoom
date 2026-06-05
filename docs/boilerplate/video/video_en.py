import json
from pathlib import Path

from manim import *

from video_style import (
    BG,
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
    title_bar,
    undim,
)


ROOT = Path(__file__).resolve().parent
DURATIONS_FILE = ROOT / "audio" / "en" / "durations.json"
SEGMENTS_FILE = ROOT / "segments_en.json"
BEATS_FILE = ROOT / "beats_en.json"


def load_json(path, fallback):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return fallback


def load_segments():
    data = load_json(SEGMENTS_FILE, {"segments": []})
    return {segment["key"]: segment["text"] for segment in data["segments"]}


DURATIONS = load_json(DURATIONS_FILE, {})
SEGMENT_TEXT = load_segments()
BEATS = load_json(BEATS_FILE, {})


def duration(key, fallback):
    return float(DURATIONS.get(key, fallback))


def fade_group(*items):
    return VGroup(*[item for item in items if item is not None])


class EnglishVideoScene(Scene):
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

    def beats(self):
        return BEATS.get(self.scene_key, [])


class Scene1_HookEN(EnglishVideoScene):
    scene_key = "Scene1_HookEN"
    fallback_duration = 28

    def construct(self):
        self.begin_sync()
        bg = make_background()
        title = title_bar("Hook")
        command = code_card("$ example", width=3.2, color=USER).move_to(LEFT * 3 + UP * 0.8)
        mechanism = card("hidden\nmechanism", width=2.4, color=KERNEL).move_to(ORIGIN + UP * 0.8)
        result = card("result", width=2.2, color=SUCCESS).move_to(RIGHT * 3 + UP * 0.8)
        path = VGroup(connect(command, mechanism, USER), connect(mechanism, result, KERNEL))
        dot = flow_dot(path[0], USER)
        summary = Text("Replace with the final takeaway", font_size=30, color=TEXT).to_edge(DOWN, buff=0.8)

        self.add(bg)
        self.play_until(0.08, FadeIn(title), FadeIn(command, shift=UP * 0.12))
        self.play_until(0.35, FadeIn(mechanism, shift=UP * 0.12), Create(path[0]), FadeIn(dot))
        self.play_until(0.62, MoveAlongPath(dot, path[0]), FadeIn(result, shift=UP * 0.12), Create(path[1]), rate_func=linear)
        self.play_until(0.84, MoveAlongPath(dot, path[1]), dim(command), undim(result), FadeIn(summary), rate_func=linear)
        self.finish_sync()
        self.play(FadeOut(fade_group(bg, title, command, mechanism, result, path, dot, summary)), run_time=0.7)


class Scene2_ConceptEN(EnglishVideoScene):
    scene_key = "Scene2_ConceptEN"
    fallback_duration = 28

    def construct(self):
        self.begin_sync()
        bg = make_background()
        title = title_bar("Core Concept")
        left = card("part A", color=USER).move_to(LEFT * 2.2)
        right = card("part B", color=KERNEL).move_to(RIGHT * 2.2)
        path = connect(left, right, KERNEL)
        summary = Text("Replace with the concept summary", font_size=30, color=TEXT).to_edge(DOWN, buff=0.8)

        self.add(bg)
        self.play_until(0.12, FadeIn(title), FadeIn(left, shift=UP * 0.12))
        self.play_until(0.48, FadeIn(right, shift=UP * 0.12), Create(path))
        self.play_until(0.86, dim(left), right.animate.set_stroke(KERNEL, width=4), FadeIn(summary))
        self.finish_sync()
        self.play(FadeOut(fade_group(bg, title, left, right, path, summary)), run_time=0.7)


class Scene3_RecapEN(EnglishVideoScene):
    scene_key = "Scene3_RecapEN"
    fallback_duration = 20

    def construct(self):
        self.begin_sync()
        bg = make_background()
        title = title_bar("Recap")
        items = VGroup(
            card("1. idea", width=2.4, color=USER),
            card("2. mechanism", width=2.8, color=KERNEL),
            card("3. result", width=2.4, color=SUCCESS),
        ).arrange(DOWN, buff=0.22).move_to(ORIGIN)

        self.add(bg)
        self.play_until(0.12, FadeIn(title))
        self.play_until(0.35, FadeIn(items[0], shift=UP * 0.12))
        self.play_until(0.58, FadeIn(items[1], shift=UP * 0.12))
        self.play_until(0.84, FadeIn(items[2], shift=UP * 0.12))
        self.finish_sync()
        self.play(FadeOut(fade_group(bg, title, items)), run_time=0.7)
