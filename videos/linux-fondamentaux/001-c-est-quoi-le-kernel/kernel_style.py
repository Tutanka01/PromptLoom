from manim import *


BG = "#10131A"
PANEL = "#171C26"
TEXT = "#F5F7FA"
MUTED = "#B7C0CE"
USER = "#3A86FF"
KERNEL = "#FFBE0B"
DANGER = "#FB5607"
MEMORY = "#06D6A0"
HARDWARE = "#6C757D"
PURPLE = "#9B5DE5"


def t(label, size=30, color=TEXT, weight=None):
    kwargs = {"font": "Arial", "font_size": size, "color": color}
    if weight is not None:
        kwargs["weight"] = weight
    return Text(label, **kwargs)


def card(label, width=3.2, height=1.0, color=USER, font_size=26):
    box = RoundedRectangle(
        width=width,
        height=height,
        corner_radius=0.12,
        stroke_color=color,
        stroke_width=2,
        fill_color=PANEL,
        fill_opacity=0.92,
    )
    text = t(label, font_size, TEXT)
    return VGroup(box, text)


def hardware_box(label, icon_label, width=2.35):
    box = RoundedRectangle(
        width=width,
        height=1.2,
        corner_radius=0.1,
        stroke_color=HARDWARE,
        stroke_width=2,
        fill_color="#202733",
        fill_opacity=1,
    )
    icon = t(icon_label, 30, KERNEL)
    label_text = t(label, 20, TEXT)
    group = VGroup(icon, label_text).arrange(DOWN, buff=0.08)
    return VGroup(box, group)


def kernel_badge(label="KERNEL"):
    outer = Circle(radius=1.08, color=KERNEL, stroke_width=5)
    inner = Circle(radius=0.72, color=KERNEL, stroke_width=2).set_fill("#2A220B", opacity=0.95)
    label_text = t(label, 29, KERNEL, BOLD)
    return VGroup(outer, inner, label_text)
