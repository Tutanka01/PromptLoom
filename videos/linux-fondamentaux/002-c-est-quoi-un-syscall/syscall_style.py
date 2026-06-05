from manim import *


FONT = "Helvetica Neue"
MONO = "Menlo"

H1 = 42
H2 = 30
BODY = 25
CAP = 20
CODE = 22

BG = "#0D1017"
BG_TOP = "#12161F"
PANEL = "#151A24"
PANEL_2 = "#202733"
EDGE = "#2A3344"
TEXT = "#ECF1F8"
MUTED = "#8A95A6"
USER = "#3A86FF"
KERNEL = "#FFBE0B"
SUCCESS = "#06D6A0"
DANGER = "#FB5607"
HARDWARE = "#6C757D"
PURPLE = "#9B5DE5"
DIM_OPACITY = 0.32


def make_background():
    base = Rectangle(width=config.frame_width + 0.2, height=config.frame_height + 0.2)
    base.set_fill(BG, opacity=1).set_stroke(width=0)
    top = Rectangle(width=config.frame_width + 0.2, height=config.frame_height * 0.42)
    top.set_fill(BG_TOP, opacity=0.55).set_stroke(width=0).to_edge(UP, buff=-0.05)
    dots = VGroup()
    for x in [i * 0.8 - 6.4 for i in range(17)]:
        for y in [i * 0.8 - 3.2 for i in range(9)]:
            dots.add(Dot([x, y, 0], radius=0.01, color="#303848").set_opacity(0.25))
    return VGroup(base, top, dots)


def t(label, size=30, color=TEXT, weight=None, font=FONT):
    kwargs = {"font": font, "font_size": size, "color": color}
    if weight is not None:
        kwargs["weight"] = weight
    return Text(label, **kwargs)


def mono(label, size=28, color=TEXT, weight=None):
    return t(label, size=size, color=color, weight=weight, font=MONO)


def _shadow_for(box):
    shadow = box.copy()
    shadow.set_stroke(width=0).set_fill("#000000", opacity=0.34)
    shadow.shift(DR * 0.055)
    return shadow


def shadowed_card(label, width=3.0, height=0.95, color=USER, font_size=BODY, fill=PANEL, radius=0.14, mono_text=False):
    box = RoundedRectangle(
        width=width,
        height=height,
        corner_radius=radius,
        stroke_color=EDGE,
        stroke_width=2,
        fill_color=fill,
        fill_opacity=0.96,
    )
    label_text = mono(label, font_size, TEXT) if mono_text else t(label, font_size, TEXT)
    label_text.move_to(box)
    accent = Line(box.get_corner(DL) + RIGHT * 0.22, box.get_corner(DR) + LEFT * 0.22, color=color, stroke_width=3)
    accent.set_opacity(0.9)
    return VGroup(_shadow_for(box), box, accent, label_text)


def card(label, width=3.0, height=0.95, color=USER, font_size=24, fill=PANEL):
    return shadowed_card(label, width=width, height=height, color=color, font_size=font_size, fill=fill)


def code_card(label, width=3.2, height=0.86, color=USER, font_size=22):
    return shadowed_card(label, width=width, height=height, color=color, font_size=font_size, fill="#111722", radius=0.1, mono_text=True)


def hardware_box(label, icon_label, width=2.25, height=1.1):
    box = RoundedRectangle(
        width=width,
        height=height,
        corner_radius=0.12,
        stroke_color=EDGE,
        stroke_width=2,
        fill_color=PANEL_2,
        fill_opacity=1,
    )
    icon = t(icon_label, 28, KERNEL, BOLD)
    label_text = t(label, 19, TEXT)
    group = VGroup(icon, label_text).arrange(DOWN, buff=0.07).move_to(box)
    accent = Line(box.get_corner(DL) + RIGHT * 0.2, box.get_corner(DR) + LEFT * 0.2, color=HARDWARE, stroke_width=3)
    return VGroup(_shadow_for(box), box, accent, group)


def kernel_badge(label="KERNEL"):
    shadow = Circle(radius=1.04, color="#000000", stroke_width=0).set_fill("#000000", opacity=0.28).shift(DR * 0.055)
    outer = Circle(radius=1.02, color=KERNEL, stroke_width=5)
    inner = Circle(radius=0.69, color=KERNEL, stroke_width=2).set_fill("#2A220B", opacity=0.96)
    label_text = t(label, 27, KERNEL, BOLD).move_to(inner)
    return VGroup(shadow, outer, inner, label_text)


def title_bar(label):
    title = t(label, 34, TEXT, BOLD).to_edge(UP, buff=0.34)
    line = Line(LEFT * 6.25, RIGHT * 6.25, color="#2D3646", stroke_width=2)
    line.next_to(title, DOWN, buff=0.18)
    return VGroup(title, line)


def arrow(start, end, color=KERNEL, stroke_width=3):
    return Arrow(start, end, buff=0.12, color=color, stroke_width=stroke_width, max_tip_length_to_length_ratio=0.14)


def connect(a, b, color=KERNEL, start_dir=RIGHT, end_dir=LEFT, stroke_width=3.5, buff=0.14):
    start = a.get_boundary_point(start_dir)
    end = b.get_boundary_point(end_dir)
    return Arrow(start, end, buff=buff, color=color, stroke_width=stroke_width, max_tip_length_to_length_ratio=0.14)


def glow(mob, color=KERNEL, layers=4, buff=0.12):
    glows = VGroup()
    for i in range(layers):
        rect = SurroundingRectangle(mob, color=color, buff=buff + i * 0.055, corner_radius=0.14)
        rect.set_stroke(color=color, width=max(1.0, 4 - i), opacity=0.22 / (i + 1))
        glows.add(rect)
    return glows


def dim(mob, opacity=DIM_OPACITY):
    return mob.animate.set_opacity(opacity)


def undim(mob):
    return mob.animate.set_opacity(1)


def focus(mob, color=KERNEL):
    return AnimationGroup(mob.animate.set_opacity(1), FadeIn(glow(mob, color), scale=1.02), lag_ratio=0)


def flow_dot(path, color=KERNEL, radius=0.07):
    dot = Dot(path.get_start(), radius=radius, color=color)
    dot.set_z_index(10)
    return dot
