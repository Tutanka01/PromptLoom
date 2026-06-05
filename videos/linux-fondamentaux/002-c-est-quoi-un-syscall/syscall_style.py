from manim import *


BG = "#10131A"
PANEL = "#171C26"
PANEL_2 = "#202733"
TEXT = "#F5F7FA"
MUTED = "#B7C0CE"
USER = "#3A86FF"
KERNEL = "#FFBE0B"
SUCCESS = "#06D6A0"
DANGER = "#FB5607"
HARDWARE = "#6C757D"
PURPLE = "#9B5DE5"


def t(label, size=30, color=TEXT, weight=None, font="Arial"):
    kwargs = {"font": font, "font_size": size, "color": color}
    if weight is not None:
        kwargs["weight"] = weight
    return Text(label, **kwargs)


def mono(label, size=28, color=TEXT, weight=None):
    return t(label, size=size, color=color, weight=weight, font="Menlo")


def card(label, width=3.0, height=0.95, color=USER, font_size=24, fill=PANEL):
    box = RoundedRectangle(
        width=width,
        height=height,
        corner_radius=0.12,
        stroke_color=color,
        stroke_width=2,
        fill_color=fill,
        fill_opacity=0.94,
    )
    label_text = t(label, font_size, TEXT)
    label_text.move_to(box)
    return VGroup(box, label_text)


def code_card(label, width=3.2, height=0.86, color=USER, font_size=22):
    box = RoundedRectangle(
        width=width,
        height=height,
        corner_radius=0.1,
        stroke_color=color,
        stroke_width=2,
        fill_color="#111722",
        fill_opacity=1,
    )
    label_text = mono(label, font_size, TEXT)
    label_text.move_to(box)
    return VGroup(box, label_text)


def hardware_box(label, icon_label, width=2.25, height=1.1):
    box = RoundedRectangle(
        width=width,
        height=height,
        corner_radius=0.1,
        stroke_color=HARDWARE,
        stroke_width=2,
        fill_color=PANEL_2,
        fill_opacity=1,
    )
    icon = t(icon_label, 28, KERNEL, BOLD)
    label_text = t(label, 19, TEXT)
    group = VGroup(icon, label_text).arrange(DOWN, buff=0.07).move_to(box)
    return VGroup(box, group)


def kernel_badge(label="KERNEL"):
    outer = Circle(radius=1.02, color=KERNEL, stroke_width=5)
    inner = Circle(radius=0.69, color=KERNEL, stroke_width=2).set_fill("#2A220B", opacity=0.96)
    label_text = t(label, 27, KERNEL, BOLD).move_to(inner)
    return VGroup(outer, inner, label_text)


def title_bar(label):
    title = t(label, 36, TEXT, BOLD).to_edge(UP, buff=0.32)
    line = Line(LEFT * 6.25, RIGHT * 6.25, color="#2D3646", stroke_width=2)
    line.next_to(title, DOWN, buff=0.16)
    return VGroup(title, line)


def arrow(start, end, color=KERNEL, stroke_width=3):
    return Arrow(start, end, buff=0.12, color=color, stroke_width=stroke_width, max_tip_length_to_length_ratio=0.08)
