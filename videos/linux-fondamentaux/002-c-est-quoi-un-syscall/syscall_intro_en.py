import json
from pathlib import Path

from manim import *

from syscall_style import (
    BG,
    DANGER,
    HARDWARE,
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
    hardware_box,
    kernel_badge,
    mono,
    t,
    title_bar,
)


ROOT = Path(__file__).resolve().parent
DURATIONS_FILE = ROOT / "audio" / "en" / "durations.json"
SEGMENTS_FILE = ROOT / "segments_en.json"


def load_durations():
    if DURATIONS_FILE.exists():
        return json.loads(DURATIONS_FILE.read_text(encoding="utf-8"))
    return {}


def load_segments():
    if not SEGMENTS_FILE.exists():
        return {}
    data = json.loads(SEGMENTS_FILE.read_text(encoding="utf-8"))
    return {segment["key"]: segment["text"] for segment in data["segments"]}


DURATIONS = load_durations()
SEGMENT_TEXT = load_segments()


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
        text = SEGMENT_TEXT.get(self.scene_key)
        if text:
            self.add_subcaption(text, duration=duration(self.scene_key, self.fallback_duration))

    def finish_sync(self, trailing_animation=0.7):
        target = duration(self.scene_key, self.fallback_duration)
        elapsed = self.time - self._sync_start
        self.wait(max(0, target - elapsed - trailing_animation))


class Scene1_HookEN(EnglishSyscallScene):
    scene_key = "Scene1_HookEN"
    fallback_duration = 35

    def construct(self):
        self.begin_sync()
        title = title_bar("A command is not direct")
        cmd = code_card("$ cat notes.txt", width=4.2, height=0.78, color=USER, font_size=25).to_edge(UP, buff=1.15)
        app = card("program", width=2.25, color=USER, font_size=23).move_to(LEFT * 4.85 + UP * 0.15)
        libc = card("libc\nwrapper", width=2.15, height=1.1, color=PURPLE, font_size=20).move_to(LEFT * 2.65 + UP * 0.15)
        gate = card("syscall\ngate", width=2.05, height=1.1, color=KERNEL, font_size=20).move_to(LEFT * 0.35 + UP * 0.15)
        kernel = kernel_badge("KERNEL").scale(0.85).move_to(RIGHT * 2.05 + UP * 0.15)
        disk = hardware_box("storage", "NVMe", width=2.2).move_to(RIGHT * 4.85 + UP * 0.15)
        flow = VGroup(app, libc, gate, kernel, disk)
        arrows = VGroup(*[arrow(a.get_right(), b.get_left(), color=c) for a, b, c in zip(flow[:-1], flow[1:], [USER, PURPLE, KERNEL, HARDWARE])])

        self.play(FadeIn(title), FadeIn(cmd, shift=DOWN * 0.15), run_time=1.4)
        self.play(LaggedStart(*[FadeIn(item, shift=UP * 0.15) for item in flow], lag_ratio=0.12), run_time=1.8)
        self.play(LaggedStart(*[Create(a) for a in arrows], lag_ratio=0.15), run_time=1.8)

        forbidden = DashedLine(app.get_bottom(), disk.get_bottom(), color=DANGER, stroke_width=3).shift(DOWN * 0.95)
        no = VGroup(
            Line(LEFT * 0.22 + DOWN * 0.22, RIGHT * 0.22 + UP * 0.22, color=DANGER, stroke_width=5),
            Line(LEFT * 0.22 + UP * 0.22, RIGHT * 0.22 + DOWN * 0.22, color=DANGER, stroke_width=5),
        ).move_to(forbidden)
        label = t("user code asks; the kernel performs", 35, TEXT, BOLD).to_edge(DOWN, buff=0.78)
        protected = VGroup(
            pill("disk", HARDWARE),
            pill("memory", SUCCESS),
            pill("network", PURPLE),
            pill("processes", KERNEL, width=1.9),
        ).arrange(RIGHT, buff=0.22).next_to(label, UP, buff=0.38)
        self.play(Create(forbidden), FadeIn(no, scale=0.7), run_time=1.2)
        self.play(LaggedStart(*[FadeIn(item, shift=UP * 0.15) for item in protected], lag_ratio=0.13), Write(label), run_time=2.0)
        self.play(Circumscribe(gate, color=KERNEL), Circumscribe(kernel, color=KERNEL), run_time=1.6)
        self.finish_sync()
        self.play(FadeOut(fade_group(title, cmd, flow, arrows, forbidden, no, label, protected)), run_time=0.7)


class Scene2_PrivilegeBoundaryEN(EnglishSyscallScene):
    scene_key = "Scene2_PrivilegeBoundaryEN"
    fallback_duration = 36

    def construct(self):
        self.begin_sync()
        title = title_bar("User mode and kernel mode")
        user_zone = RoundedRectangle(width=12.2, height=2.35, corner_radius=0.12, color=USER, stroke_width=2).set_fill("#12243E", 0.82).shift(UP * 1.35)
        kernel_zone = RoundedRectangle(width=12.2, height=2.35, corner_radius=0.12, color=KERNEL, stroke_width=2).set_fill("#2A220B", 0.82).shift(DOWN * 1.35)
        boundary = DashedLine(LEFT * 6.15, RIGHT * 6.15, color=TEXT, stroke_width=3)
        labels = VGroup(
            t("USER MODE", 28, USER, BOLD).move_to(user_zone.get_left() + RIGHT * 1.55 + UP * 0.75),
            t("KERNEL MODE", 28, KERNEL, BOLD).move_to(kernel_zone.get_left() + RIGHT * 1.75 + DOWN * 0.75),
        )
        apps = VGroup(
            card("browser", width=1.85, height=0.65, color=USER, font_size=18),
            card("shell", width=1.65, height=0.65, color=USER, font_size=18),
            card("editor", width=1.75, height=0.65, color=USER, font_size=18),
            card("database", width=2.05, height=0.65, color=USER, font_size=18),
        ).arrange(RIGHT, buff=0.23).move_to(UP * 1.3 + RIGHT * 1.5)
        kernel = kernel_badge("Linux\nkernel").scale(0.8).move_to(DOWN * 1.35 + LEFT * 2.4)
        powers = VGroup(
            pill("hardware", HARDWARE, width=1.7),
            pill("memory", SUCCESS, width=1.55),
            pill("scheduler", PURPLE, width=1.85),
            pill("isolation", KERNEL, width=1.75),
        ).arrange(RIGHT, buff=0.18).move_to(DOWN * 1.35 + RIGHT * 2.35)

        self.play(FadeIn(title), FadeIn(user_zone), FadeIn(kernel_zone), Create(boundary), Write(labels), run_time=1.8)
        self.play(FadeIn(apps, shift=DOWN * 0.15), FadeIn(kernel, scale=0.75), FadeIn(powers, shift=UP * 0.15), run_time=1.8)
        bad_jump = Arrow(apps[0].get_bottom(), kernel.get_top(), buff=0.08, color=DANGER, stroke_width=4)
        blocked = t("direct jump blocked", 24, DANGER, BOLD).next_to(boundary, UP, buff=0.18).shift(LEFT * 2.2)
        gate = card("CPU entry\npath", width=2.05, height=1.0, color=KERNEL, font_size=19).move_to(ORIGIN + RIGHT * 1.3)
        down = Arrow(apps[1].get_bottom(), gate.get_top(), buff=0.08, color=KERNEL, stroke_width=4)
        up = Arrow(gate.get_bottom(), kernel.get_top(), buff=0.08, color=KERNEL, stroke_width=4)
        ret = CurvedArrow(kernel.get_right(), apps[2].get_bottom(), angle=-TAU / 5, color=SUCCESS, stroke_width=3)
        self.play(Create(bad_jump), Write(blocked), run_time=1.2)
        self.play(bad_jump.animate.set_opacity(0.25), FadeIn(gate, scale=0.8), run_time=0.9)
        self.play(Create(down), Create(up), Circumscribe(gate, color=KERNEL), run_time=1.5)
        self.play(Create(ret), Write(t("return to user mode", 24, SUCCESS, BOLD).next_to(ret, RIGHT, buff=0.2)), run_time=1.5)
        self.finish_sync()
        self.play(FadeOut(fade_group(title, user_zone, kernel_zone, boundary, labels, apps, kernel, powers, bad_jump, blocked, gate, down, up, ret)), run_time=0.7)


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
        same_process = t("same process\nsame privilege", 22, MUTED).next_to(stack, DOWN, buff=0.45)
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

        self.play(FadeIn(title), Write(left_title), Write(right_title), run_time=1.2)
        self.play(LaggedStart(*[FadeIn(frame, shift=UP * 0.12) for frame in stack], lag_ratio=0.12), Write(same_process), run_time=1.8)
        self.play(FadeIn(wrapper, shift=DOWN * 0.15), LaggedStart(*[FadeIn(reg, shift=LEFT * 0.12) for reg in registers], lag_ratio=0.09), run_time=2.2)
        self.play(FadeIn(instr, scale=0.85), Circumscribe(registers, color=KERNEL), run_time=1.4)
        path = VGroup(
            arrow(instr.get_right(), entry.get_left(), DANGER),
            arrow(entry.get_left(), handler.get_right(), KERNEL),
            CurvedArrow(handler.get_top(), wrapper.get_bottom(), angle=-TAU / 5, color=SUCCESS, stroke_width=3),
        )
        self.play(FadeIn(entry), FadeIn(handler), Create(path[0]), run_time=1.3)
        self.play(Create(path[1]), Create(path[2]), run_time=1.5)
        result = code_card("return: bytes or -errno", width=3.35, height=0.64, color=SUCCESS, font_size=18).next_to(handler, DOWN, buff=0.36)
        self.play(FadeIn(result, shift=UP * 0.1), Circumscribe(instr, color=DANGER), run_time=1.4)
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

        self.play(FadeIn(title), FadeIn(columns), run_time=1.1)
        self.play(LaggedStart(*[FadeIn(row, shift=UP * 0.12) for row in rows], lag_ratio=0.09), run_time=2.2)
        highlights = VGroup(SurroundingRectangle(rows[0], color=KERNEL, buff=0.06), SurroundingRectangle(rows[2], color=KERNEL, buff=0.06), SurroundingRectangle(rows[5], color=KERNEL, buff=0.06))
        self.play(Create(highlights[0]), run_time=0.8)
        self.play(ReplacementTransform(highlights[0], highlights[1]), run_time=0.8)
        self.play(ReplacementTransform(highlights[1], highlights[2]), run_time=0.8)
        self.play(LaggedStart(*[FadeIn(note, shift=UP * 0.15) for note in notes], lag_ratio=0.16), run_time=1.5)
        arrows = VGroup(arrow(abi.get_right(), validate.get_left(), MUTED), arrow(validate.get_right(), ret.get_left(), MUTED))
        self.play(Create(arrows), Circumscribe(columns, color=MUTED), run_time=1.4)
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

        self.play(FadeIn(title), FadeIn(process), FadeIn(call), run_time=1.5)
        self.play(LaggedStart(*[FadeIn(row, shift=RIGHT * 0.12) for row in fd_table], lag_ratio=0.12), Write(fd_label), run_time=1.7)
        self.play(FadeIn(open_file, shift=RIGHT * 0.15), Create(arrow(fd_table[3].get_right(), open_file.get_left(), SUCCESS)), run_time=1.2)
        arrows = VGroup(*[arrow(a.get_right(), b.get_left(), c) for a, b, c in zip(chain[:-1], chain[1:], [KERNEL, PURPLE, KERNEL])])
        self.play(FadeIn(vfs), FadeIn(fs), FadeIn(driver), FadeIn(disk), run_time=1.5)
        self.play(LaggedStart(*[Create(a) for a in arrows], lag_ratio=0.14), Create(arrow(driver.get_top(), disk.get_bottom(), HARDWARE)), run_time=1.7)
        readwrite = VGroup(
            code_card("read(3, buf, n)", width=2.75, height=0.58, color=KERNEL, font_size=16),
            code_card("write(1, buf, n)", width=2.75, height=0.58, color=KERNEL, font_size=16),
        ).arrange(RIGHT, buff=0.35).to_edge(DOWN, buff=0.74).shift(RIGHT * 1.1)
        label = t("after open, the path becomes a small handle", 28, TEXT, BOLD).next_to(readwrite, UP, buff=0.28)
        self.play(FadeIn(readwrite, shift=UP * 0.15), Write(label), Circumscribe(fd_table[3], color=SUCCESS), run_time=1.8)
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

        self.play(FadeIn(title), FadeIn(request, shift=RIGHT * 0.15), run_time=1.4)
        self.play(LaggedStart(*[FadeIn(c, shift=UP * 0.12) for c in checks], lag_ratio=0.11), run_time=1.8)
        self.play(LaggedStart(*[Create(a) for a in arrows], lag_ratio=0.12), run_time=1.6)
        self.play(FadeIn(allowed, shift=UP * 0.12), Create(arrow(checks[-1].get_bottom(), allowed.get_top(), SUCCESS)), run_time=1.2)
        self.play(FadeIn(denied, shift=UP * 0.12), FadeIn(errno), Create(arrow(checks[-1].get_bottom(), denied.get_top(), DANGER)), run_time=1.3)
        self.play(FadeIn(examples, shift=UP * 0.12), Circumscribe(checks[-1], color=DANGER), run_time=1.5)
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

        self.play(FadeIn(title), FadeIn(proc), FadeIn(call), FadeIn(waitq), run_time=1.5)
        self.play(Create(arrow(call.get_right(), waitq.get_left(), KERNEL)), FadeIn(sleeping, shift=DOWN * 0.1), run_time=1.3)
        self.play(FadeIn(scheduler), Create(arrow(waitq.get_right(), scheduler.get_left(), KERNEL)), FadeIn(proc_b, shift=LEFT * 0.15), run_time=1.6)
        self.play(FadeIn(nic), FadeIn(interrupt), Create(arrow(nic.get_right(), interrupt.get_left(), DANGER)), Flash(interrupt, color=DANGER), run_time=1.6)
        wake_path = VGroup(arrow(interrupt.get_top(), waitq.get_bottom(), DANGER), arrow(waitq.get_right(), proc.get_right(), SUCCESS))
        self.play(Create(wake_path), ReplacementTransform(sleeping, runnable), run_time=1.6)
        self.play(FadeIn(result, shift=UP * 0.12), Create(arrow(proc.get_bottom(), result.get_left(), SUCCESS)), Circumscribe(waitq, color=KERNEL), run_time=1.5)
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

        self.play(FadeIn(title), FadeIn(shell), run_time=1.0)
        flow = VGroup(shell, fork, child, execve, program)
        self.play(LaggedStart(*[FadeIn(item, shift=RIGHT * 0.12) for item in flow[1:]], lag_ratio=0.16), run_time=2.0)
        self.play(LaggedStart(*[Create(arrow(a.get_right(), b.get_left(), KERNEL)) for a, b in zip(flow[:-1], flow[1:])], lag_ratio=0.15), run_time=1.7)
        self.play(FadeIn(wait), FadeIn(exit_box), Create(arrow(program.get_bottom(), exit_box.get_top(), DANGER)), Create(arrow(exit_box.get_left(), wait.get_right(), SUCCESS)), run_time=1.6)
        self.play(LaggedStart(*[FadeIn(obj, shift=UP * 0.12) for obj in objects], lag_ratio=0.08), run_time=1.7)
        summary = t("launching an app creates kernel-managed objects", 29, TEXT, BOLD).next_to(objects, UP, buff=0.28)
        self.play(Write(summary), Circumscribe(child, color=SUCCESS), run_time=1.4)
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

        self.play(FadeIn(title), FadeIn(process), LaggedStart(*[FadeIn(r, shift=UP * 0.1) for r in regions], lag_ratio=0.08), run_time=1.9)
        self.play(FadeIn(mmap), FadeIn(kernel), FadeIn(table), Create(arrow(mmap.get_right(), kernel.get_left(), KERNEL)), Create(arrow(kernel.get_right(), table.get_left(), SUCCESS)), run_time=1.8)
        self.play(FadeIn(pages), FadeIn(ram), Create(arrow(table.get_bottom(), pages.get_top(), SUCCESS)), run_time=1.4)
        self.play(FadeIn(fault, shift=UP * 0.12), Create(arrow(regions[2].get_right(), fault.get_left(), DANGER)), Flash(fault, color=DANGER), run_time=1.5)
        self.play(FadeIn(allocate, shift=UP * 0.12), Create(arrow(fault.get_bottom(), allocate.get_top(), SUCCESS)), Circumscribe(pages[3], color=DANGER), run_time=1.6)
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

        self.play(FadeIn(title), FadeIn(app), LaggedStart(*[FadeIn(c, shift=UP * 0.1) for c in calls], lag_ratio=0.08), run_time=1.7)
        self.play(FadeIn(fd), Create(arrow(calls.get_right(), fd.get_left(), SUCCESS)), run_time=1.2)
        self.play(FadeIn(stack), FadeIn(nic), FadeIn(internet), run_time=1.6)
        path = VGroup(arrow(fd.get_right(), stack.get_left(), KERNEL), arrow(stack.get_right(), nic.get_left(), HARDWARE), arrow(nic.get_right(), internet.get_left(), PURPLE))
        self.play(LaggedStart(*[Create(a) for a in path], lag_ratio=0.16), run_time=1.7)
        self.play(FadeIn(buffers, shift=UP * 0.12), Create(arrow(calls[2].get_bottom(), buffers[0].get_left(), SUCCESS)), Create(arrow(buffers[1].get_top(), calls[3].get_bottom(), PURPLE)), run_time=1.6)
        self.play(Circumscribe(stack, color=KERNEL), Flash(nic, color=DANGER), run_time=1.5)
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

        self.play(FadeIn(title), FadeIn(terminal), Write(term_title), run_time=1.2)
        self.play(LaggedStart(*[FadeIn(line, shift=UP * 0.08) for line in logs], lag_ratio=0.12), run_time=1.6)
        self.play(FadeIn(seccomp, shift=LEFT * 0.12), FadeIn(sandbox, shift=LEFT * 0.12), Create(arrow(seccomp.get_right(), sandbox.get_left(), PURPLE)), run_time=1.5)
        self.play(FadeIn(allow), FadeIn(deny), Circumscribe(seccomp, color=DANGER), run_time=1.4)
        self.play(Write(cost_label), LaggedStart(*[FadeIn(item, shift=UP * 0.12) for item in timeline], lag_ratio=0.1), run_time=1.8)
        self.play(FadeIn(batching, shift=UP * 0.12), Circumscribe(timeline[1], color=KERNEL), run_time=1.5)
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

        self.play(FadeIn(title), LaggedStart(*[FadeIn(step, shift=UP * 0.1) for step in steps], lag_ratio=0.08), run_time=1.9)
        self.play(LaggedStart(*[Create(a) for a in arrows], lag_ratio=0.09), run_time=1.5)
        self.play(FadeIn(kernel, scale=0.75), Circumscribe(steps[3], color=DANGER), run_time=1.4)
        self.play(LaggedStart(*[FadeIn(ex, shift=UP * 0.1) for ex in examples], lag_ratio=0.08), run_time=1.8)
        self.play(Write(final), Circumscribe(kernel, color=KERNEL), run_time=1.6)
        self.finish_sync()
        self.play(FadeOut(fade_group(title, steps, arrows, kernel, examples, final)), run_time=0.7)
