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
    return VGroup(base, top)


def t(label, size=BODY, color=TEXT, weight=None, font=FONT):
    kwargs = {"font": font, "font_size": size, "color": color}
    if weight is not None:
        kwargs["weight"] = weight
    return Text(label, **kwargs)


def mono(label, size=CODE, color=TEXT, weight=None):
    return t(label, size=size, color=color, weight=weight, font=MONO)


def _shadow_for(box):
    shadow = box.copy()
    shadow.set_stroke(width=0).set_fill("#000000", opacity=0.34)
    shadow.shift(DR * 0.055)
    return shadow


def card(label, width=3.0, height=0.95, color=USER, font_size=BODY, fill=PANEL):
    box = RoundedRectangle(
        width=width,
        height=height,
        corner_radius=0.14,
        stroke_color=EDGE,
        stroke_width=2,
        fill_color=fill,
        fill_opacity=0.96,
    )
    label_text = t(label, font_size, TEXT).move_to(box)
    accent = Line(box.get_corner(DL) + RIGHT * 0.22, box.get_corner(DR) + LEFT * 0.22, color=color, stroke_width=3)
    return VGroup(_shadow_for(box), box, accent, label_text)


def code_card(label, width=3.2, height=0.86, color=USER, font_size=CODE):
    box = card(label, width=width, height=height, color=color, font_size=font_size, fill="#111722")
    box[-1].become(mono(label, font_size, TEXT).move_to(box[1]))
    return box


def title_bar(label):
    title = t(label, 34, TEXT, BOLD).to_edge(UP, buff=0.34)
    line = Line(LEFT * 6.25, RIGHT * 6.25, color="#2D3646", stroke_width=2)
    line.next_to(title, DOWN, buff=0.18)
    return VGroup(title, line)


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


def flow_dot(path, color=KERNEL, radius=0.07):
    dot = Dot(path.get_start(), radius=radius, color=color)
    dot.set_z_index(10)
    return dot
