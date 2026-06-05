import json
from pathlib import Path

from manim import *

from syscall_style import (
    BG,
    BODY,
    CAP,
    CODE,
    DANGER,
    EDGE,
    HARDWARE,
    H1,
    H2,
    KERNEL,
    MUTED,
    PANEL,
    PANEL_2,
    PURPLE,
    SUCCESS,
    TEXT,
    USER,
    arrow,
    card,
    code_card,
    connect,
    dim,
    flow_dot,
    glow,
    hardware_box,
    kernel_badge,
    make_background,
    mono,
    t,
    title_bar,
    undim,
)


ROOT = Path(__file__).resolve().parent
DURATIONS_FILE = ROOT / "audio" / "en" / "durations.json"
SEGMENTS_FILE = ROOT / "segments_en.json"
BEATS_FILE = ROOT / "beats_en.json"


def load_durations():
    if DURATIONS_FILE.exists():
        return json.loads(DURATIONS_FILE.read_text(encoding="utf-8"))
    return {}


def load_segments():
    if not SEGMENTS_FILE.exists():
        return {}
    data = json.loads(SEGMENTS_FILE.read_text(encoding="utf-8"))
    return {segment["key"]: segment["text"] for segment in data["segments"]}


def load_beats():
    if not BEATS_FILE.exists():
        return {}
    return json.loads(BEATS_FILE.read_text(encoding="utf-8"))


DURATIONS = load_durations()
SEGMENT_TEXT = load_segments()
BEATS = load_beats()


def duration(key: str, fallback: float) -> float:
    return float(DURATIONS.get(key, fallback))


def fade_group(*items):
    return VGroup(*[item for item in items if item is not None])


def pill(label, color, width=1.55):
    box = RoundedRectangle(
        width=width,
        height=0.48,
        corner_radius=0.2,
        stroke_color=color,
        stroke_width=2,
        fill_color=PANEL_2,
        fill_opacity=1,
    )
    text = t(label, 17, TEXT, BOLD).move_to(box)
    return VGroup(box, text)


class EnglishSyscallScene(Scene):
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

    def finish_sync(self, trailing_animation=0.7):
        target = self.scene_duration()
        elapsed = self.time - self._sync_start
        self.wait(max(0, target - elapsed - trailing_animation))

    def scene_duration(self):
        return getattr(self, "_scene_duration", duration(self.scene_key, self.fallback_duration))

    def cue(self, ratio):
        return self._sync_start + self.scene_duration() * ratio

    def hold_until(self, ratio):
        self.wait(max(0, self.cue(ratio) - self.time))

    def play_until(self, ratio, *animations, min_run_time=0.25, rate_func=smooth):
        run_time = max(min_run_time, self.cue(ratio) - self.time)
        self.play(*animations, run_time=run_time, rate_func=rate_func)

    def beats(self):
        return BEATS.get(self.scene_key, [])


class Scene1_HookEN(EnglishSyscallScene):
    scene_key = "Scene1_HookEN"
    fallback_duration = 35

    def construct(self):
        self.begin_sync()
        bg = make_background()
        title = title_bar("A command is not direct")
        terminal = RoundedRectangle(width=7.2, height=1.05, corner_radius=0.16, color=USER, stroke_width=2)
        terminal.set_fill("#101722", opacity=1).to_edge(UP, buff=1.12)
        prompt = mono("$ cat notes.txt", CODE + 4, TEXT).move_to(terminal)
        cursor = Rectangle(width=0.08, height=0.46, color=USER, stroke_width=0).set_fill(USER, opacity=1)
        cursor.next_to(prompt, RIGHT, buff=0.16)

        user_zone = RoundedRectangle(width=3.0, height=2.25, corner_radius=0.18, color=USER, stroke_width=2)
        user_zone.set_fill("#12243E", opacity=0.35).move_to(LEFT * 4.35 + UP * 0.05)
        user_label = t("user space", CAP, USER, BOLD).next_to(user_zone, UP, buff=0.16)
        app = card("program", width=2.25, height=0.9, color=USER, font_size=BODY).move_to(user_zone)

        disk = hardware_box("storage", "NVMe", width=2.25, height=1.15).move_to(RIGHT * 4.65 + UP * 0.05)
        direct = DashedLine(app.get_right(), disk.get_left(), color=DANGER, stroke_width=3).shift(DOWN * 1.0)
        direct_label = t("direct hardware command", CAP, DANGER, BOLD).next_to(direct, DOWN, buff=0.18)
        no = VGroup(
            Line(LEFT * 0.22 + DOWN * 0.22, RIGHT * 0.22 + UP * 0.22, color=DANGER, stroke_width=6),
            Line(LEFT * 0.22 + UP * 0.22, RIGHT * 0.22 + DOWN * 0.22, color=DANGER, stroke_width=6),
        ).move_to(direct)

        resources = VGroup(
            pill("disk", HARDWARE, width=1.25),
            pill("memory", SUCCESS, width=1.55),
            pill("network", PURPLE, width=1.7),
            pill("processes", KERNEL, width=1.9),
        ).arrange(RIGHT, buff=0.24).to_edge(DOWN, buff=1.05)

        libc = card("libc\nwrapper", width=2.05, height=1.05, color=PURPLE, font_size=CAP).move_to(LEFT * 2.25 + UP * 0.05)
        gate = card("syscall\ngate", width=2.05, height=1.05, color=KERNEL, font_size=CAP).move_to(ORIGIN + UP * 0.05)
        kernel = kernel_badge("KERNEL").scale(0.82).move_to(RIGHT * 2.25 + UP * 0.05)
        flow = VGroup(app, libc, gate, kernel, disk)
        paths = VGroup(
            connect(app, libc, USER),
            connect(libc, gate, PURPLE),
            connect(gate, kernel, KERNEL),
            connect(kernel, disk, HARDWARE),
        )
        token_box = RoundedRectangle(width=0.74, height=0.34, corner_radius=0.08, color=USER, stroke_width=3)
        token_box.set_fill("#16345A", opacity=1)
        token_lines = VGroup(
            Line(LEFT * 0.18, RIGHT * 0.18, color=TEXT, stroke_width=2),
            Line(LEFT * 0.14, RIGHT * 0.14, color=TEXT, stroke_width=2),
        ).arrange(DOWN, buff=0.08).move_to(token_box)
        token = VGroup(token_box, token_lines).move_to(paths[0].get_start())
        token.set_z_index(10)
        summary = t("user code asks; the kernel performs", 34, TEXT, BOLD).to_edge(DOWN, buff=0.44)

        focus_glow = None
        self.add(bg)
        self.play_until(0.08, FadeIn(title), FadeIn(terminal, shift=DOWN * 0.12), Write(prompt), FadeIn(cursor))
        self.play_until(0.20, FadeIn(VGroup(user_zone, user_label, app), shift=RIGHT * 0.2), FadeIn(disk, shift=LEFT * 0.2), Create(direct), Write(direct_label))

        focus_glow = glow(VGroup(direct, direct_label), DANGER)
        self.play_until(
            0.36,
            FadeIn(no, scale=0.75),
            FadeIn(focus_glow),
            LaggedStart(*[FadeIn(item, shift=UP * 0.12) for item in resources], lag_ratio=0.12),
            dim(disk),
        )
        self.play_until(0.50, FadeOut(focus_glow), undim(app), dim(VGroup(disk, resources, direct, direct_label, no)), user_zone.animate.set_stroke(USER, width=4).set_fill("#12243E", opacity=0.72))

        self.play_until(0.62, FadeIn(VGroup(libc, gate, kernel), shift=UP * 0.16), FadeOut(VGroup(direct_label)), undim(disk), undim(resources), user_zone.animate.set_stroke(USER, width=2).set_fill("#12243E", opacity=0.35))
        self.play_until(0.68, LaggedStart(*[Create(path) for path in paths], lag_ratio=0.18), FadeIn(token))
        self.play_until(0.74, MoveAlongPath(token, paths[0]), gate.animate.set_stroke(PURPLE, width=3), rate_func=linear)
        self.play_until(0.80, MoveAlongPath(token, paths[1]), rate_func=linear)
        self.play_until(0.86, MoveAlongPath(token, paths[2]), kernel.animate.scale(1.08), rate_func=linear)
        self.play_until(0.88, MoveAlongPath(token, paths[3]), disk.animate.set_opacity(1), rate_func=linear)

        final_glow = glow(VGroup(gate, kernel), KERNEL)
        self.play_until(0.94, FadeIn(final_glow), Write(summary), dim(VGroup(app, libc, disk, resources)))
        self.finish_sync()
        self.play(FadeOut(fade_group(bg, title, terminal, prompt, cursor, user_zone, user_label, flow, paths, token, direct, no, resources, summary, final_glow)), run_time=0.7)


class Scene2_PrivilegeBoundaryEN(EnglishSyscallScene):
    scene_key = "Scene2_PrivilegeBoundaryEN"
    fallback_duration = 36

    def construct(self):
        self.begin_sync()
        bg = make_background()
        title = title_bar("User mode and kernel mode")
        user_zone = RoundedRectangle(width=12.1, height=2.35, corner_radius=0.16, color=USER, stroke_width=2).set_fill("#12243E", 0.72).shift(UP * 1.35)
        kernel_zone = RoundedRectangle(width=12.1, height=2.35, corner_radius=0.16, color=KERNEL, stroke_width=2).set_fill("#2A220B", 0.72).shift(DOWN * 1.35)
        boundary = DashedLine(LEFT * 6.1, RIGHT * 6.1, color=TEXT, stroke_width=3)
        labels = VGroup(
            t("USER MODE", H2, USER, BOLD).move_to(user_zone.get_left() + RIGHT * 1.65 + UP * 0.72),
            t("KERNEL MODE", H2, KERNEL, BOLD).move_to(kernel_zone.get_left() + RIGHT * 1.86 + DOWN * 0.72),
        )
        apps = VGroup(
            card("browser", width=1.85, height=0.66, color=USER, font_size=18),
            card("shell", width=1.65, height=0.66, color=USER, font_size=18),
            card("editor", width=1.75, height=0.66, color=USER, font_size=18),
            card("database", width=2.05, height=0.66, color=USER, font_size=18),
        ).arrange(RIGHT, buff=0.24).move_to(UP * 1.3 + RIGHT * 1.55)
        kernel = kernel_badge("Linux\nkernel").scale(0.78).move_to(DOWN * 1.35 + LEFT * 2.45)
        powers = VGroup(
            pill("hardware", HARDWARE, width=1.7),
            pill("memory", SUCCESS, width=1.55),
            pill("scheduler", PURPLE, width=1.85),
            pill("isolation", KERNEL, width=1.75),
        ).arrange(RIGHT, buff=0.2).move_to(DOWN * 1.35 + RIGHT * 2.35)

        cpu_chip = RoundedRectangle(width=2.35, height=0.7, corner_radius=0.14, color=HARDWARE, stroke_width=2)
        cpu_chip.set_fill(PANEL_2, opacity=0.94).move_to(UP * 0.05 + LEFT * 4.55)
        cpu_label = t("CPU privilege levels", CAP, TEXT, BOLD).move_to(cpu_chip)

        bad_jump = Arrow(apps[0].get_bottom(), kernel.get_top(), buff=0.08, color=DANGER, stroke_width=4, max_tip_length_to_length_ratio=0.14)
        blocked = t("direct jump blocked", CAP + 2, DANGER, BOLD).next_to(boundary, UP, buff=0.18).shift(LEFT * 2.2)
        block_mark = VGroup(
            Line(LEFT * 0.18 + DOWN * 0.18, RIGHT * 0.18 + UP * 0.18, color=DANGER, stroke_width=5),
            Line(LEFT * 0.18 + UP * 0.18, RIGHT * 0.18 + DOWN * 0.18, color=DANGER, stroke_width=5),
        ).move_to(boundary.get_center() + LEFT * 1.55)

        gate = card("CPU entry\npath", width=2.05, height=1.0, color=KERNEL, font_size=CAP).move_to(ORIGIN + RIGHT * 1.3)
        request = Dot(apps[1].get_bottom(), radius=0.075, color=KERNEL).set_z_index(10)
        down = Arrow(apps[1].get_bottom(), gate.get_top(), buff=0.08, color=KERNEL, stroke_width=4, max_tip_length_to_length_ratio=0.14)
        up = Arrow(gate.get_bottom(), kernel.get_top(), buff=0.08, color=KERNEL, stroke_width=4, max_tip_length_to_length_ratio=0.14)
        ret = CurvedArrow(kernel.get_right(), apps[2].get_bottom(), angle=-TAU / 5, color=SUCCESS, stroke_width=3.5)
        ret_label = t("return to user mode", CAP + 1, SUCCESS, BOLD).move_to(RIGHT * 4.2 + UP * 0.25)

        self.add(bg)
        self.play_until(0.08, FadeIn(title), FadeIn(cpu_chip, shift=RIGHT * 0.15), Write(cpu_label))
        self.play_until(0.24, FadeIn(user_zone), FadeIn(kernel_zone), Create(boundary), Write(labels), FadeIn(apps, shift=DOWN * 0.12), FadeOut(VGroup(cpu_chip, cpu_label)))

        kernel_focus = glow(VGroup(kernel, powers), KERNEL)
        self.play_until(0.40, FadeIn(kernel, scale=0.75), LaggedStart(*[FadeIn(power, shift=UP * 0.12) for power in powers], lag_ratio=0.12), FadeIn(kernel_focus))
        self.play_until(0.56, FadeOut(kernel_focus), Create(bad_jump), FadeIn(block_mark, scale=0.8), Write(blocked), dim(powers))
        self.play_until(0.64, bad_jump.animate.set_opacity(0.22), FadeIn(gate, scale=0.8), FadeOut(block_mark), undim(powers))

        gate_focus = glow(gate, KERNEL)
        self.play_until(0.74, Create(down), Create(up), FadeIn(request), FadeIn(gate_focus), dim(VGroup(apps[0], apps[3], powers)))
        self.play_until(0.81, MoveAlongPath(request, down), rate_func=linear)
        self.play_until(0.87, MoveAlongPath(request, up), rate_func=linear)
        self.play_until(0.92, Create(ret), FadeIn(ret_label, shift=LEFT * 0.12), request.animate.move_to(apps[2].get_bottom()), FadeOut(gate_focus), undim(VGroup(apps[0], apps[3], powers)))
        final_focus = glow(VGroup(down, up, ret, gate), SUCCESS)
        self.play_until(0.95, FadeIn(final_focus), kernel_zone.animate.set_stroke(KERNEL, width=4), user_zone.animate.set_stroke(USER, width=4))
        self.finish_sync()
        self.play(FadeOut(fade_group(bg, title, cpu_chip, cpu_label, user_zone, kernel_zone, boundary, labels, apps, kernel, powers, bad_jump, blocked, gate, down, up, ret, ret_label, request, final_focus)), run_time=0.7)


class Scene3_NotAFunctionCallEN(EnglishSyscallScene):
    scene_key = "Scene3_NotAFunctionCallEN"
    fallback_duration = 39

    def construct(self):
        self.begin_sync()
        title = title_bar("A syscall is not a normal function call")
        left_title = t("normal call", 28, USER, BOLD).move_to(LEFT * 3.7 + UP * 2.35)
        right_title = t("syscall path", 28, KERNEL, BOLD).move_to(RIGHT * 3.55 + UP * 2.35)
        stack = VGroup(
            code_card("main()", width=2.6, height=0.58, color=USER, font_size=18),
            code_card("parse()", width=2.6, height=0.58, color=USER, font_size=18),
            code_card("helper()", width=2.6, height=0.58, color=USER, font_size=18),
            code_card("return", width=2.6, height=0.58, color=SUCCESS, font_size=18),
        ).arrange(DOWN, buff=0.12).move_to(LEFT * 3.7 + UP * 0.55)
        same_process = VGroup(
            pill("same process", USER, width=2.25).scale(0.88),
            pill("same privilege", SUCCESS, width=2.35).scale(0.88),
        ).arrange(DOWN, buff=0.1).next_to(stack, DOWN, buff=0.38)
        wrapper = code_card("libc: read(fd, buf, n)", width=4.35, color=PURPLE, font_size=18).move_to(RIGHT * 3.4 + UP * 1.45)
        registers = VGroup(
            code_card("rax = SYS_read", width=2.55, height=0.52, color=KERNEL, font_size=15),
            code_card("rdi = fd", width=2.55, height=0.52, color=KERNEL, font_size=15),
            code_card("rsi = buf", width=2.55, height=0.52, color=KERNEL, font_size=15),
            code_card("rdx = count", width=2.55, height=0.52, color=KERNEL, font_size=15),
        ).arrange(DOWN, buff=0.09).next_to(wrapper, DOWN, buff=0.35)
        instr = code_card("syscall", width=2.05, height=0.7, color=DANGER, font_size=23).next_to(registers, DOWN, buff=0.38)
        entry = card("kernel\nentry", width=2.15, height=0.95, color=KERNEL, font_size=20).move_to(RIGHT * 5.35 + DOWN * 1.15)
        handler = card("handler\nreturns result", width=2.55, height=0.95, color=SUCCESS, font_size=19).move_to(RIGHT * 2.65 + DOWN * 1.15)

        self.play_until(0.08, FadeIn(title), Write(left_title), Write(right_title))
        self.play_until(0.23, LaggedStart(*[FadeIn(frame, shift=UP * 0.12) for frame in stack], lag_ratio=0.12), FadeIn(same_process, shift=UP * 0.08))
        self.play_until(0.38, FadeIn(wrapper, shift=DOWN * 0.15), LaggedStart(*[FadeIn(reg, shift=LEFT * 0.12) for reg in registers], lag_ratio=0.09))
        self.play_until(0.52, FadeIn(instr, scale=0.85), Circumscribe(registers, color=KERNEL))
        path = VGroup(
            arrow(instr.get_right(), entry.get_left(), DANGER),
            arrow(entry.get_left(), handler.get_right(), KERNEL),
            CurvedArrow(handler.get_top(), wrapper.get_bottom(), angle=-TAU / 5, color=SUCCESS, stroke_width=3),
        )
        self.play_until(0.66, FadeIn(entry), FadeIn(handler), Create(path[0]))
        self.play_until(0.80, Create(path[1]), Create(path[2]))
        result = code_card("return: bytes or -errno", width=3.35, height=0.64, color=SUCCESS, font_size=18).next_to(handler, DOWN, buff=0.36)
        self.play_until(0.90, FadeIn(result, shift=UP * 0.1), Circumscribe(instr, color=DANGER))
        self.finish_sync()
        self.play(FadeOut(fade_group(title, left_title, right_title, stack, same_process, wrapper, registers, instr, entry, handler, path, result)), run_time=0.7)


class Scene4_SyscallTableEN(EnglishSyscallScene):
    scene_key = "Scene4_SyscallTableEN"
    fallback_duration = 36

    def construct(self):
        self.begin_sync()
        title = title_bar("The syscall table")
        columns = VGroup(t("number", 20, MUTED, BOLD), t("name", 20, MUTED, BOLD), t("kernel handler", 20, MUTED, BOLD)).arrange(RIGHT, buff=1.35)
        columns.move_to(UP * 2.23)
        rows = VGroup()
        data = [
            ("0", "read", "ksys_read"),
            ("1", "write", "ksys_write"),
            ("257", "openat", "do_sys_openat2"),
            ("9", "mmap", "ksys_mmap_pgoff"),
            ("56", "clone", "kernel_clone"),
            ("59", "execve", "do_execveat_common"),
        ]
        for nr, name, handler in data:
            row_box = RoundedRectangle(width=8.6, height=0.52, corner_radius=0.08, color="#2D3646", stroke_width=1.4).set_fill(PANEL, 0.9)
            row = VGroup(mono(nr, 17, KERNEL), mono(name, 17, TEXT), mono(handler, 17, SUCCESS))
            row.arrange(RIGHT, buff=1.15)
            row[0].align_to(columns[0], LEFT)
            row[1].align_to(columns[1], LEFT)
            row[2].align_to(columns[2], LEFT)
            row.move_to(row_box)
            rows.add(VGroup(row_box, row))
        rows.arrange(DOWN, buff=0.12).move_to(UP * 0.05)
        abi = card("user-kernel ABI", width=3.3, height=0.75, color=KERNEL, font_size=23).to_edge(DOWN, buff=0.72).shift(LEFT * 3.1)
        validate = card("validate args", width=2.8, height=0.75, color=DANGER, font_size=23).to_edge(DOWN, buff=0.72)
        ret = card("return value", width=2.8, height=0.75, color=SUCCESS, font_size=23).to_edge(DOWN, buff=0.72).shift(RIGHT * 3.1)
        notes = VGroup(abi, validate, ret)

        self.play_until(0.08, FadeIn(title), FadeIn(columns))
        self.play_until(0.28, LaggedStart(*[FadeIn(row, shift=UP * 0.12) for row in rows], lag_ratio=0.09))
        highlights = VGroup(SurroundingRectangle(rows[0], color=KERNEL, buff=0.06), SurroundingRectangle(rows[2], color=KERNEL, buff=0.06), SurroundingRectangle(rows[5], color=KERNEL, buff=0.06))
        self.play_until(0.40, Create(highlights[0]))
        self.play_until(0.52, ReplacementTransform(highlights[0], highlights[1]))
        self.play_until(0.64, ReplacementTransform(highlights[1], highlights[2]))
        self.play_until(0.78, LaggedStart(*[FadeIn(note, shift=UP * 0.15) for note in notes], lag_ratio=0.16))
        arrows = VGroup(arrow(abi.get_right(), validate.get_left(), MUTED), arrow(validate.get_right(), ret.get_left(), MUTED))
        self.play_until(0.90, Create(arrows), Circumscribe(columns, color=MUTED))
        self.finish_sync()
        self.play(FadeOut(fade_group(title, columns, rows, highlights[2], notes, arrows)), run_time=0.7)


class Scene5_FileDescriptorsEN(EnglishSyscallScene):
    scene_key = "Scene5_FileDescriptorsEN"
    fallback_duration = 43

    def construct(self):
        self.begin_sync()
        title = title_bar("Files and file descriptors")
        process = card("process", width=2.45, color=USER, font_size=24).to_edge(LEFT, buff=0.75).shift(UP * 0.8)
        call = code_card('openat("notes.txt")', width=3.3, height=0.65, color=USER, font_size=17).next_to(process, DOWN, buff=0.35)
        fd_table = VGroup(
            code_card("0 stdin", width=2.3, height=0.45, color=MUTED, font_size=14),
            code_card("1 stdout", width=2.3, height=0.45, color=MUTED, font_size=14),
            code_card("2 stderr", width=2.3, height=0.45, color=MUTED, font_size=14),
            code_card("3 notes.txt", width=2.3, height=0.45, color=SUCCESS, font_size=14),
        ).arrange(DOWN, buff=0.07).next_to(call, DOWN, buff=0.35)
        fd_label = t("fd table", 20, MUTED).next_to(fd_table, DOWN, buff=0.16)
        open_file = card("open file\ndescription", width=2.45, height=1.05, color=SUCCESS, font_size=19).move_to(LEFT * 1.35 + DOWN * 0.25)
        vfs = card("VFS", width=1.75, height=0.8, color=KERNEL, font_size=23).move_to(RIGHT * 0.85 + DOWN * 0.25)
        fs = card("ext4\nor xfs", width=1.9, height=0.95, color=PURPLE, font_size=19).move_to(RIGHT * 2.75 + DOWN * 0.25)
        driver = card("block\ndriver", width=2.05, height=0.95, color=KERNEL, font_size=19).move_to(RIGHT * 4.65 + DOWN * 0.25)
        disk = hardware_box("storage", "SSD", width=1.75, height=0.95).move_to(RIGHT * 5.75 + UP * 1.25)
        chain = VGroup(open_file, vfs, fs, driver)

        self.play_until(0.10, FadeIn(title), FadeIn(process), FadeIn(call))
        self.play_until(0.25, LaggedStart(*[FadeIn(row, shift=RIGHT * 0.12) for row in fd_table], lag_ratio=0.12), Write(fd_label))
        self.play_until(0.40, FadeIn(open_file, shift=RIGHT * 0.15), Create(arrow(fd_table[3].get_right(), open_file.get_left(), SUCCESS)))
        arrows = VGroup(*[arrow(a.get_right(), b.get_left(), c) for a, b, c in zip(chain[:-1], chain[1:], [KERNEL, PURPLE, KERNEL])])
        self.play_until(0.55, FadeIn(vfs), FadeIn(fs), FadeIn(driver), FadeIn(disk))
        self.play_until(0.70, LaggedStart(*[Create(a) for a in arrows], lag_ratio=0.14), Create(arrow(driver.get_top(), disk.get_bottom(), HARDWARE)))
        readwrite = VGroup(
            code_card("read(3, buf, n)", width=2.75, height=0.58, color=KERNEL, font_size=16),
            code_card("write(1, buf, n)", width=2.75, height=0.58, color=KERNEL, font_size=16),
        ).arrange(RIGHT, buff=0.35).to_edge(DOWN, buff=0.74).shift(RIGHT * 1.1)
        label = t("after open, the path becomes a small handle", 28, TEXT, BOLD).next_to(readwrite, UP, buff=0.28)
        self.play_until(0.90, FadeIn(readwrite, shift=UP * 0.15), Write(label), Circumscribe(fd_table[3], color=SUCCESS))
        self.finish_sync()
        self.play(FadeOut(fade_group(title, process, call, fd_table, fd_label, open_file, vfs, fs, driver, disk, arrows, readwrite, label)), run_time=0.7)


class Scene6_PermissionsErrorsEN(EnglishSyscallScene):
    scene_key = "Scene6_PermissionsErrorsEN"
    fallback_duration = 38

    def construct(self):
        self.begin_sync()
        title = title_bar("Every syscall is a checkpoint")
        request = code_card('openat("/etc/shadow", O_RDONLY)', width=5.15, height=0.72, color=USER, font_size=18).to_edge(LEFT, buff=0.75).shift(UP * 1.45)
        checks = VGroup(
            card("credentials\nuid/gid", width=2.2, height=0.92, color=USER, font_size=18),
            card("path\nlookup", width=2.0, height=0.92, color=PURPLE, font_size=18),
            card("flags\nmode", width=1.9, height=0.92, color=KERNEL, font_size=18),
            card("mount\npolicy", width=2.0, height=0.92, color=SUCCESS, font_size=18),
            card("LSM\nhooks", width=1.8, height=0.92, color=DANGER, font_size=18),
        ).arrange(RIGHT, buff=0.18).move_to(UP * 0.15)
        arrows = VGroup()
        arrows.add(arrow(request.get_right(), checks[0].get_left(), USER))
        for a, b in zip(checks[:-1], checks[1:]):
            arrows.add(arrow(a.get_right(), b.get_left(), MUTED, stroke_width=2.5))
        allowed = card("success\nfd >= 0", width=2.3, height=0.9, color=SUCCESS, font_size=20).move_to(RIGHT * 3.7 + DOWN * 1.55)
        denied = card("denied\n-EACCES", width=2.3, height=0.9, color=DANGER, font_size=20).move_to(LEFT * 1.0 + DOWN * 1.55)
        errno = code_card("libc sets errno", width=2.7, height=0.58, color=DANGER, font_size=17).next_to(denied, DOWN, buff=0.25)
        examples = VGroup(
            code_card("kill(pid, SIGTERM)", width=2.85, height=0.52, color=PURPLE, font_size=15),
            code_card("ptrace(...)", width=2.1, height=0.52, color=PURPLE, font_size=15),
        ).arrange(RIGHT, buff=0.25).to_edge(DOWN, buff=0.55).shift(LEFT * 3.1)

        self.play_until(0.10, FadeIn(title), FadeIn(request, shift=RIGHT * 0.15))
        self.play_until(0.25, LaggedStart(*[FadeIn(c, shift=UP * 0.12) for c in checks], lag_ratio=0.11))
        self.play_until(0.40, LaggedStart(*[Create(a) for a in arrows], lag_ratio=0.12))
        self.play_until(0.55, FadeIn(allowed, shift=UP * 0.12), Create(arrow(checks[-1].get_bottom(), allowed.get_top(), SUCCESS)))
        self.play_until(0.68, FadeIn(denied, shift=UP * 0.12), FadeIn(errno), Create(arrow(checks[-1].get_bottom(), denied.get_top(), DANGER)))
        self.play_until(0.88, FadeIn(examples, shift=UP * 0.12), Circumscribe(checks[-1], color=DANGER))
        self.finish_sync()
        self.play(FadeOut(fade_group(title, request, checks, arrows, allowed, denied, errno, examples)), run_time=0.7)


class Scene7_BlockingWakeupsEN(EnglishSyscallScene):
    scene_key = "Scene7_BlockingWakeupsEN"
    fallback_duration = 39

    def construct(self):
        self.begin_sync()
        title = title_bar("Blocking syscalls let the CPU do other work")
        proc = card("process A", width=2.45, color=USER, font_size=23).move_to(LEFT * 4.4 + UP * 1.05)
        call = code_card("read(socket)", width=2.7, height=0.62, color=USER, font_size=18).next_to(proc, DOWN, buff=0.3)
        waitq = card("socket\nwait queue", width=2.35, height=1.0, color=KERNEL, font_size=19).move_to(LEFT * 1.55 + UP * 0.1)
        sleeping = pill("sleeping", DANGER, width=1.65).next_to(proc, UP, buff=0.18)
        scheduler = card("scheduler", width=2.5, height=0.84, color=KERNEL, font_size=23).move_to(RIGHT * 1.15 + UP * 0.1)
        proc_b = card("process B\nruns", width=2.35, height=1.0, color=SUCCESS, font_size=20).move_to(RIGHT * 4.25 + UP * 0.1)
        nic = hardware_box("network card", "NIC", width=2.3, height=1.05).move_to(LEFT * 4.25 + DOWN * 1.65)
        interrupt = card("interrupt", width=2.15, height=0.78, color=DANGER, font_size=22).move_to(LEFT * 1.55 + DOWN * 1.65)
        runnable = pill("runnable again", SUCCESS, width=2.2).next_to(proc, UP, buff=0.18)
        result = code_card("read returns bytes", width=3.0, height=0.62, color=SUCCESS, font_size=18).move_to(RIGHT * 3.7 + DOWN * 1.65)

        self.play_until(0.10, FadeIn(title), FadeIn(proc), FadeIn(call), FadeIn(waitq))
        self.play_until(0.25, Create(arrow(call.get_right(), waitq.get_left(), KERNEL)), FadeIn(sleeping, shift=DOWN * 0.1))
        self.play_until(0.40, FadeIn(scheduler), Create(arrow(waitq.get_right(), scheduler.get_left(), KERNEL)), FadeIn(proc_b, shift=LEFT * 0.15))
        self.play_until(0.55, FadeIn(nic), FadeIn(interrupt), Create(arrow(nic.get_right(), interrupt.get_left(), DANGER)), Flash(interrupt, color=DANGER))
        wake_path = VGroup(arrow(interrupt.get_top(), waitq.get_bottom(), DANGER), arrow(waitq.get_right(), proc.get_right(), SUCCESS))
        self.play_until(0.70, Create(wake_path), ReplacementTransform(sleeping, runnable))
        self.play_until(0.88, FadeIn(result, shift=UP * 0.12), Create(arrow(proc.get_bottom(), result.get_left(), SUCCESS)), Circumscribe(waitq, color=KERNEL))
        self.finish_sync()
        self.play(FadeOut(fade_group(title, proc, call, waitq, scheduler, proc_b, nic, interrupt, runnable, result, wake_path)), run_time=0.7)


class Scene8_ProcessSyscallsEN(EnglishSyscallScene):
    scene_key = "Scene8_ProcessSyscallsEN"
    fallback_duration = 41

    def construct(self):
        self.begin_sync()
        title = title_bar("Processes are built with syscalls")
        shell = card("shell\nPID 1200", width=2.45, height=1.0, color=USER, font_size=19).to_edge(LEFT, buff=0.75).shift(UP * 0.75)
        fork = code_card("fork / clone", width=2.1, height=0.7, color=KERNEL, font_size=17).move_to(LEFT * 2.6 + UP * 0.75)
        child = card("child\nPID 1201", width=2.2, height=1.0, color=SUCCESS, font_size=18).move_to(LEFT * 0.15 + UP * 0.75)
        execve = code_card("execve", width=1.65, height=0.7, color=PURPLE, font_size=17).move_to(RIGHT * 2.35 + UP * 0.75)
        program = card("new program", width=2.4, height=0.85, color=PURPLE, font_size=20).to_edge(RIGHT, buff=0.65).shift(UP * 0.75)
        wait = code_card("wait()", width=1.75, height=0.62, color=KERNEL, font_size=17).move_to(LEFT * 2.6 + DOWN * 1.65)
        exit_box = code_card("exit(status)", width=2.25, height=0.62, color=DANGER, font_size=17).move_to(RIGHT * 2.55 + DOWN * 1.65)
        objects = VGroup(
            pill("PID", KERNEL, width=1.1),
            pill("credentials", USER, width=1.9),
            pill("memory map", SUCCESS, width=1.85),
            pill("fd table", PURPLE, width=1.55),
            pill("signals", DANGER, width=1.45),
            pill("priority", HARDWARE, width=1.45),
        ).arrange(RIGHT, buff=0.16).to_edge(DOWN, buff=0.65)

        self.play_until(0.08, FadeIn(title), FadeIn(shell))
        flow = VGroup(shell, fork, child, execve, program)
        self.play_until(0.22, LaggedStart(*[FadeIn(item, shift=RIGHT * 0.12) for item in flow[1:]], lag_ratio=0.16))
        self.play_until(0.38, LaggedStart(*[Create(arrow(a.get_right(), b.get_left(), KERNEL)) for a, b in zip(flow[:-1], flow[1:])], lag_ratio=0.15))
        self.play_until(0.54, FadeIn(wait), FadeIn(exit_box), Create(arrow(program.get_bottom(), exit_box.get_top(), DANGER)), Create(arrow(exit_box.get_left(), wait.get_right(), SUCCESS)))
        self.play_until(0.70, LaggedStart(*[FadeIn(obj, shift=UP * 0.12) for obj in objects], lag_ratio=0.08))
        summary = t("launching an app creates kernel-managed objects", 29, TEXT, BOLD).next_to(objects, UP, buff=0.28)
        self.play_until(0.88, Write(summary), Circumscribe(child, color=SUCCESS))
        self.finish_sync()
        self.play(FadeOut(fade_group(title, shell, fork, child, execve, program, wait, exit_box, objects, summary)), run_time=0.7)


class Scene9_MemorySyscallsEN(EnglishSyscallScene):
    scene_key = "Scene9_MemorySyscallsEN"
    fallback_duration = 40

    def construct(self):
        self.begin_sync()
        title = title_bar("Memory syscalls and page faults")
        process = card("process address space", width=3.7, height=0.75, color=USER, font_size=22).to_edge(LEFT, buff=0.75).shift(UP * 2.0)
        regions = VGroup(
            code_card("text", width=2.6, height=0.48, color=MUTED, font_size=15),
            code_card("heap via brk", width=2.6, height=0.48, color=SUCCESS, font_size=15),
            code_card("mmap file", width=2.6, height=0.48, color=PURPLE, font_size=15),
            code_card("stack", width=2.6, height=0.48, color=USER, font_size=15),
        ).arrange(DOWN, buff=0.08).next_to(process, DOWN, buff=0.35)
        mmap = code_card("mmap(...)", width=2.35, height=0.64, color=KERNEL, font_size=18).move_to(LEFT * 0.4 + UP * 1.15)
        kernel = card("kernel records\nmapping", width=2.75, height=1.0, color=KERNEL, font_size=19).move_to(RIGHT * 2.0 + UP * 1.15)
        table = card("page\ntable", width=1.95, height=1.0, color=SUCCESS, font_size=20).move_to(RIGHT * 4.35 + UP * 1.15)
        pages = VGroup()
        for i, color in enumerate([SUCCESS, SUCCESS, PURPLE, DANGER, HARDWARE, PURPLE]):
            sq = Square(side_length=0.48, color=color, stroke_width=2).set_fill(color, opacity=0.28)
            sq.add(mono(str(i), 13, TEXT).move_to(sq))
            pages.add(sq)
        pages.arrange(RIGHT, buff=0.08).move_to(RIGHT * 3.25 + DOWN * 0.75)
        ram = card("physical RAM", width=3.1, height=0.68, color=HARDWARE, font_size=21).next_to(pages, DOWN, buff=0.35)
        fault = card("page fault\ntrap", width=2.3, height=0.9, color=DANGER, font_size=19).move_to(LEFT * 0.35 + DOWN * 1.2)
        allocate = card("allocate / load\nor reject", width=2.85, height=0.9, color=SUCCESS, font_size=19).move_to(RIGHT * 0.75 + DOWN * 2.45)

        self.play_until(0.12, FadeIn(title), FadeIn(process), LaggedStart(*[FadeIn(r, shift=UP * 0.1) for r in regions], lag_ratio=0.08))
        self.play_until(0.30, FadeIn(mmap), FadeIn(kernel), FadeIn(table), Create(arrow(mmap.get_right(), kernel.get_left(), KERNEL)), Create(arrow(kernel.get_right(), table.get_left(), SUCCESS)))
        self.play_until(0.48, FadeIn(pages), FadeIn(ram), Create(arrow(table.get_bottom(), pages.get_top(), SUCCESS)))
        self.play_until(0.66, FadeIn(fault, shift=UP * 0.12), Create(arrow(regions[2].get_right(), fault.get_left(), DANGER)), Flash(fault, color=DANGER))
        self.play_until(0.84, FadeIn(allocate, shift=UP * 0.12), Create(arrow(fault.get_bottom(), allocate.get_top(), SUCCESS)), Circumscribe(pages[3], color=DANGER))
        self.finish_sync()
        self.play(FadeOut(fade_group(title, process, regions, mmap, kernel, table, pages, ram, fault, allocate)), run_time=0.7)


class Scene10_NetworkSyscallsEN(EnglishSyscallScene):
    scene_key = "Scene10_NetworkSyscallsEN"
    fallback_duration = 37

    def construct(self):
        self.begin_sync()
        title = title_bar("Network syscalls")
        app = card("web client", width=2.4, color=USER, font_size=23).to_edge(LEFT, buff=0.78).shift(UP * 0.95)
        calls = VGroup(
            code_card("socket()", width=2.25, height=0.52, color=USER, font_size=15),
            code_card("connect()", width=2.25, height=0.52, color=USER, font_size=15),
            code_card("send()", width=2.25, height=0.52, color=USER, font_size=15),
            code_card("recv()", width=2.25, height=0.52, color=USER, font_size=15),
        ).arrange(DOWN, buff=0.08).next_to(app, DOWN, buff=0.35)
        fd = card("socket fd", width=2.25, height=0.75, color=SUCCESS, font_size=22).move_to(LEFT * 1.7 + UP * 0.15)
        stack = VGroup(
            card("TCP", width=1.7, height=0.58, color=KERNEL, font_size=18),
            card("IP", width=1.7, height=0.58, color=KERNEL, font_size=18),
            card("routing", width=1.9, height=0.58, color=KERNEL, font_size=18),
            card("driver", width=1.85, height=0.58, color=KERNEL, font_size=18),
        ).arrange(DOWN, buff=0.08).move_to(RIGHT * 0.65 + UP * 0.15)
        nic = hardware_box("network card", "NIC", width=2.2, height=1.0).move_to(RIGHT * 3.1 + UP * 0.15)
        internet = VGroup(Circle(radius=0.72, color=PURPLE, stroke_width=3).set_fill("#201833", 0.9), t("peer", 24, TEXT, BOLD)).move_to(RIGHT * 5.25 + UP * 0.15)
        buffers = VGroup(card("kernel\nbuffers", width=2.25, height=0.9, color=SUCCESS, font_size=19), card("packets", width=2.05, height=0.7, color=PURPLE, font_size=21)).arrange(RIGHT, buff=0.25).to_edge(DOWN, buff=0.75).shift(RIGHT * 1.2)

        self.play_until(0.10, FadeIn(title), FadeIn(app), LaggedStart(*[FadeIn(c, shift=UP * 0.1) for c in calls], lag_ratio=0.08))
        self.play_until(0.24, FadeIn(fd), Create(arrow(calls.get_right(), fd.get_left(), SUCCESS)))
        self.play_until(0.40, FadeIn(stack), FadeIn(nic), FadeIn(internet))
        path = VGroup(arrow(fd.get_right(), stack.get_left(), KERNEL), arrow(stack.get_right(), nic.get_left(), HARDWARE), arrow(nic.get_right(), internet.get_left(), PURPLE))
        self.play_until(0.56, LaggedStart(*[Create(a) for a in path], lag_ratio=0.16))
        self.play_until(0.72, FadeIn(buffers, shift=UP * 0.12), Create(arrow(calls[2].get_bottom(), buffers[0].get_left(), SUCCESS)), Create(arrow(buffers[1].get_top(), calls[3].get_bottom(), PURPLE)))
        self.play_until(0.88, Circumscribe(stack, color=KERNEL), Flash(nic, color=DANGER))
        self.finish_sync()
        self.play(FadeOut(fade_group(title, app, calls, fd, stack, nic, internet, buffers, path)), run_time=0.7)


class Scene11_ObserveControlCostEN(EnglishSyscallScene):
    scene_key = "Scene11_ObserveControlCostEN"
    fallback_duration = 42

    def construct(self):
        self.begin_sync()
        title = title_bar("Syscalls are observable, controllable, and not free")
        terminal = RoundedRectangle(width=4.6, height=3.05, corner_radius=0.12, color=SUCCESS, stroke_width=2).set_fill("#111722", 1).to_edge(LEFT, buff=0.75).shift(UP * 0.35)
        term_title = mono("strace", 20, SUCCESS, BOLD).move_to(terminal.get_top() + DOWN * 0.28)
        logs = VGroup(
            mono('openat(...) = 3', 15, TEXT),
            mono('read(3, ...) = 4096', 15, TEXT),
            mono('write(1, ...) = 4096', 15, TEXT),
            mono('close(3) = 0', 15, TEXT),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.13).move_to(terminal).shift(DOWN * 0.22)
        seccomp = card("seccomp\nfilter", width=2.45, height=1.05, color=DANGER, font_size=20).move_to(RIGHT * 0.25 + UP * 0.85)
        allow = pill("allow: read/write", SUCCESS, width=2.35).next_to(seccomp, DOWN, buff=0.28)
        deny = pill("deny: mount", DANGER, width=1.85).next_to(allow, DOWN, buff=0.15)
        sandbox = card("container\nsandbox", width=2.35, height=1.0, color=PURPLE, font_size=20).move_to(RIGHT * 3.25 + UP * 0.85)
        timeline = VGroup(
            pill("save regs", MUTED, width=1.5),
            pill("switch mode", KERNEL, width=1.75),
            pill("check args", DANGER, width=1.65),
            pill("copy data", SUCCESS, width=1.55),
            pill("return", USER, width=1.25),
        ).arrange(RIGHT, buff=0.12).to_edge(DOWN, buff=0.9)
        cost_label = t("crossing the boundary has cost", 28, TEXT, BOLD).next_to(timeline, UP, buff=0.32)
        batching = VGroup(
            code_card("batch work", width=2.15, height=0.54, color=SUCCESS, font_size=15),
            code_card("avoid tiny calls", width=2.55, height=0.54, color=SUCCESS, font_size=15),
            code_card("async interfaces", width=2.75, height=0.54, color=SUCCESS, font_size=15),
        ).arrange(DOWN, buff=0.1).to_edge(RIGHT, buff=0.75).shift(DOWN * 0.75)

        self.play_until(0.08, FadeIn(title), FadeIn(terminal), Write(term_title))
        self.play_until(0.22, LaggedStart(*[FadeIn(line, shift=UP * 0.08) for line in logs], lag_ratio=0.12))
        self.play_until(0.36, FadeIn(seccomp, shift=LEFT * 0.12), FadeIn(sandbox, shift=LEFT * 0.12), Create(arrow(seccomp.get_right(), sandbox.get_left(), PURPLE)))
        self.play_until(0.50, FadeIn(allow), FadeIn(deny), Circumscribe(seccomp, color=DANGER))
        self.play_until(0.68, Write(cost_label), LaggedStart(*[FadeIn(item, shift=UP * 0.12) for item in timeline], lag_ratio=0.1))
        self.play_until(0.88, FadeIn(batching, shift=UP * 0.12), Circumscribe(timeline[1], color=KERNEL))
        self.finish_sync()
        self.play(FadeOut(fade_group(title, terminal, term_title, logs, seccomp, allow, deny, sandbox, timeline, cost_label, batching)), run_time=0.7)


class Scene12_RecapEN(EnglishSyscallScene):
    scene_key = "Scene12_RecapEN"
    fallback_duration = 40

    def construct(self):
        self.begin_sync()
        title = title_bar("Syscalls in one mental model")
        steps = VGroup(
            card("1. user code", width=2.35, height=0.7, color=USER, font_size=20),
            card("2. libc wrapper", width=2.55, height=0.7, color=PURPLE, font_size=20),
            card("3. number + args", width=2.75, height=0.7, color=KERNEL, font_size=20),
            card("4. CPU entry", width=2.35, height=0.7, color=DANGER, font_size=20),
            card("5. kernel handler", width=2.8, height=0.7, color=KERNEL, font_size=20),
            card("6. result / errno", width=2.75, height=0.7, color=SUCCESS, font_size=20),
        ).arrange(DOWN, buff=0.13).to_edge(LEFT, buff=0.75).shift(UP * 0.1)
        arrows = VGroup(*[Arrow(a.get_bottom(), b.get_top(), buff=0.07, color=MUTED, stroke_width=2.4, max_tip_length_to_length_ratio=0.12) for a, b in zip(steps[:-1], steps[1:])])
        kernel = kernel_badge("syscall\nboundary").scale(0.95).move_to(RIGHT * 1.3 + UP * 0.45)
        examples = VGroup(
            pill("files", SUCCESS, width=1.2),
            pill("processes", KERNEL, width=1.75),
            pill("memory", PURPLE, width=1.45),
            pill("network", USER, width=1.55),
            pill("clocks", HARDWARE, width=1.25),
            pill("signals", DANGER, width=1.35),
            pill("permissions", KERNEL, width=1.95),
        ).arrange_in_grid(rows=3, cols=3, buff=(0.22, 0.18)).move_to(RIGHT * 4.1 + UP * 0.5)
        final = t("controlled doorway for protected operations", 34, TEXT, BOLD).to_edge(DOWN, buff=0.86).shift(RIGHT * 1.15)

        self.play_until(0.12, FadeIn(title), LaggedStart(*[FadeIn(step, shift=UP * 0.1) for step in steps], lag_ratio=0.08))
        self.play_until(0.30, LaggedStart(*[Create(a) for a in arrows], lag_ratio=0.09))
        self.play_until(0.48, FadeIn(kernel, scale=0.75), Circumscribe(steps[3], color=DANGER))
        self.play_until(0.68, LaggedStart(*[FadeIn(ex, shift=UP * 0.1) for ex in examples], lag_ratio=0.08))
        self.play_until(0.90, Write(final), Circumscribe(kernel, color=KERNEL))
        self.finish_sync()
        self.play(FadeOut(fade_group(title, steps, arrows, kernel, examples, final)), run_time=0.7)
