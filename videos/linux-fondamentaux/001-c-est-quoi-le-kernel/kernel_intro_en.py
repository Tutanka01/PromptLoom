import json
from pathlib import Path

from manim import *

from kernel_intro import (
    BG,
    DANGER,
    HARDWARE,
    KERNEL,
    MEMORY,
    MUTED,
    PANEL,
    PURPLE,
    TEXT,
    USER,
    card,
    hardware_box,
    kernel_badge,
    t,
)


ROOT = Path(__file__).resolve().parent
DURATIONS_FILE = ROOT / "audio" / "en" / "durations.json"


def load_durations():
    if DURATIONS_FILE.exists():
        return json.loads(DURATIONS_FILE.read_text(encoding="utf-8"))
    return {}


DURATIONS = load_durations()


def duration(key: str, fallback: float) -> float:
    return float(DURATIONS.get(key, fallback))


class EnglishKernelScene(Scene):
    scene_key = ""
    fallback_duration = 25.0

    def setup(self):
        self.camera.background_color = BG

    def title(self, label):
        title = t(label, 38, TEXT, BOLD).to_edge(UP, buff=0.32)
        line = Line(LEFT * 6.3, RIGHT * 6.3, color="#2D3646", stroke_width=2).next_to(title, DOWN, buff=0.18)
        return VGroup(title, line)

    def begin_sync(self):
        self._sync_start = self.time

    def finish_sync(self, trailing_animation=0.7):
        target = duration(self.scene_key, self.fallback_duration)
        elapsed = self.time - self._sync_start
        self.wait(max(0, target - elapsed - trailing_animation))


class Scene1_HookEN(EnglishKernelScene):
    scene_key = "Scene1_HookEN"
    fallback_duration = 18

    def construct(self):
        self.begin_sync()
        self.add_subcaption("Open an app. Click a file. It feels direct, but it is not.", duration=8)
        app = card("Application", width=3.8, height=1.25, color=USER, font_size=32)
        request = t('open "photo.png"', 30, TEXT).next_to(app, DOWN, buff=0.45)
        cursor = Triangle(color=KERNEL, fill_opacity=1).scale(0.16).rotate(-PI / 2).next_to(request, LEFT, buff=0.18)
        self.play(FadeIn(app, shift=UP * 0.25), Write(request), FadeIn(cursor), run_time=1.6)
        self.wait(0.8)

        self.add_subcaption("Your app does not talk straight to the disk, the CPU, or memory.", duration=8)
        layers = VGroup(
            card("user space", width=5.0, height=0.8, color=USER, font_size=25),
            card("kernel", width=5.0, height=0.8, color=KERNEL, font_size=25),
            card("hardware", width=5.0, height=0.8, color=HARDWARE, font_size=25),
        ).arrange(DOWN, buff=0.14).move_to(ORIGIN)
        self.play(
            ReplacementTransform(app, layers[0]),
            ReplacementTransform(request, layers[1]),
            cursor.animate.move_to(layers[2].get_left() + LEFT * 0.35),
            run_time=2.0,
        )
        self.play(FadeIn(layers[2], shift=DOWN * 0.2), run_time=0.8)
        glow = SurroundingRectangle(layers[1], color=KERNEL, buff=0.12, stroke_width=4)
        question = t("Who really controls the machine?", 44, TEXT, BOLD).to_edge(DOWN, buff=0.7)
        self.play(Create(glow), Write(question), run_time=1.6)
        self.finish_sync()
        self.play(FadeOut(VGroup(layers, glow, question, cursor)), run_time=0.7)


class Scene2_HardwareChaosEN(EnglishKernelScene):
    scene_key = "Scene2_HardwareChaosEN"
    fallback_duration = 20

    def construct(self):
        self.begin_sync()
        title = self.title("Without a kernel, programs fight the hardware")
        apps = VGroup(
            card("browser", color=USER, font_size=23),
            card("terminal", color=USER, font_size=23),
            card("music", color=USER, font_size=23),
        ).arrange(DOWN, buff=0.25).to_edge(LEFT, buff=0.8)
        hw = VGroup(
            hardware_box("CPU", "CPU"),
            hardware_box("RAM", "RAM"),
            hardware_box("DISK", "IO"),
            hardware_box("NET", "IP"),
        ).arrange(DOWN, buff=0.18).to_edge(RIGHT, buff=0.75)
        arrows = VGroup()
        for app in apps:
            for device in hw:
                arrows.add(Arrow(app.get_right(), device.get_left(), buff=0.12, color=DANGER, stroke_width=2.2, max_tip_length_to_length_ratio=0.06))
        self.play(FadeIn(title), FadeIn(apps, shift=RIGHT * 0.2), FadeIn(hw, shift=LEFT * 0.2), run_time=1.7)
        self.play(LaggedStart(*[Create(a) for a in arrows], lag_ratio=0.02), run_time=2.2)
        warning = t("fast, but unsafe", 42, DANGER, BOLD).to_edge(DOWN, buff=0.55)
        self.play(Write(warning), Circumscribe(arrows, color=DANGER), run_time=1.6)
        kernel = kernel_badge().move_to(ORIGIN)
        clean_arrows = VGroup(
            *[Arrow(app.get_right(), kernel.get_left(), buff=0.15, color=USER, stroke_width=3) for app in apps],
            *[Arrow(kernel.get_right(), device.get_left(), buff=0.15, color=KERNEL, stroke_width=3) for device in hw],
        )
        self.play(FadeOut(arrows), FadeOut(warning), FadeIn(kernel, scale=0.7), run_time=1.5)
        self.play(LaggedStart(*[Create(a) for a in clean_arrows], lag_ratio=0.06), run_time=1.8)
        self.finish_sync()
        self.play(FadeOut(VGroup(title, apps, hw, kernel, clean_arrows)), run_time=0.7)


class Scene3_BoundaryEN(EnglishKernelScene):
    scene_key = "Scene3_BoundaryEN"
    fallback_duration = 25

    def construct(self):
        self.begin_sync()
        title = self.title("The border: user space / kernel space")
        top = Rectangle(width=12.5, height=2.5, color=USER, stroke_width=2).set_fill("#12243E", opacity=0.7).shift(UP * 1.45)
        bottom = Rectangle(width=12.5, height=2.5, color=KERNEL, stroke_width=2).set_fill("#322808", opacity=0.7).shift(DOWN * 1.45)
        boundary = DashedLine(LEFT * 6.2, RIGHT * 6.2, color=TEXT, stroke_width=3)
        labels = VGroup(
            t("USER SPACE", 30, USER, BOLD).move_to(top.get_left() + RIGHT * 1.45 + UP * 0.85),
            t("KERNEL SPACE", 30, KERNEL, BOLD).move_to(bottom.get_left() + RIGHT * 1.65 + DOWN * 0.85),
        )
        app = card("process", color=USER, font_size=24).move_to(UP * 1.45 + LEFT * 3.8)
        kernel = kernel_badge("KERNEL").scale(0.8).move_to(DOWN * 1.45 + RIGHT * 3.7)
        gate = card("syscall", width=1.55, height=1.05, color=KERNEL, font_size=21).move_to(ORIGIN)
        self.play(FadeIn(title), FadeIn(top), FadeIn(bottom), Write(labels), Create(boundary), run_time=1.7)
        self.play(FadeIn(app), FadeIn(kernel), FadeIn(gate), run_time=1.3)
        call = t('open("photo.png")', 30, TEXT).next_to(app, DOWN, buff=0.28)
        request = Arrow(app.get_bottom(), gate.get_top(), color=USER, buff=0.1)
        into_kernel = Arrow(gate.get_bottom(), kernel.get_left(), color=KERNEL, buff=0.1)
        response = Arrow(kernel.get_top(), app.get_right(), color=MEMORY, buff=0.1)
        self.play(Write(call), Create(request), run_time=1.4)
        self.play(Circumscribe(gate, color=KERNEL), Create(into_kernel), run_time=1.4)
        checks = VGroup(t("permissions", 22), t("filesystem", 22), t("driver", 22)).arrange(RIGHT, buff=0.45).next_to(kernel, DOWN, buff=0.5)
        for item in checks:
            item.add(SurroundingRectangle(item, color=KERNEL, buff=0.15))
        self.play(Create(response), LaggedStart(*[FadeIn(item, shift=UP * 0.2) for item in checks], lag_ratio=0.18), run_time=1.9)
        self.finish_sync()
        self.play(FadeOut(VGroup(title, top, bottom, labels, boundary, app, kernel, gate, call, request, into_kernel, response, checks)), run_time=0.7)


class Scene4_SchedulerEN(EnglishKernelScene):
    scene_key = "Scene4_SchedulerEN"
    fallback_duration = 20

    def construct(self):
        self.begin_sync()
        title = self.title("The scheduler shares the CPU")
        processes = VGroup(
            card("P1 browser", color=USER, font_size=21),
            card("P2 shell", color=USER, font_size=21),
            card("P3 audio", color=USER, font_size=21),
            card("P4 server", color=USER, font_size=21),
        ).arrange(DOWN, buff=0.2).to_edge(LEFT, buff=0.7)
        scheduler = card("scheduler", width=3.1, height=0.85, color=KERNEL, font_size=25).move_to(ORIGIN + DOWN * 0.05)
        cpu = VGroup(Circle(radius=1.15, color=HARDWARE, stroke_width=4).set_fill("#202733", 1), t("CPU", 42, TEXT, BOLD)).move_to(RIGHT * 3.55)
        self.play(FadeIn(title), FadeIn(processes, shift=RIGHT * 0.2), FadeIn(scheduler), FadeIn(cpu), run_time=1.8)
        self.play(Create(Arrow(processes.get_right(), scheduler.get_left(), color=USER, buff=0.18)), Create(Arrow(scheduler.get_right(), cpu.get_left(), color=KERNEL, buff=0.18)), run_time=1.1)
        slots = VGroup()
        for name, color in zip(["P1", "P2", "P3", "P1", "P4", "P2"], [USER, MEMORY, PURPLE, DANGER, USER, MEMORY]):
            slot = Rectangle(width=1.05, height=0.55, color=color, stroke_width=2).set_fill(color, 0.45)
            slot.add(t(name, 20, TEXT, BOLD).move_to(slot))
            slots.add(slot)
        slots.arrange(RIGHT, buff=0.05).to_edge(DOWN, buff=0.72)
        self.play(Write(t("CPU time slices", 25, MUTED).next_to(slots, UP, buff=0.22)), LaggedStart(*[FadeIn(slot, shift=UP * 0.15) for slot in slots], lag_ratio=0.12), run_time=2.0)
        insight = t("multitasking = fast arbitration", 36, KERNEL, BOLD).next_to(cpu, DOWN, buff=0.6)
        self.play(Write(insight), Circumscribe(scheduler, color=KERNEL), run_time=1.7)
        self.finish_sync()
        self.play(FadeOut(VGroup(title, processes, scheduler, cpu, slots, insight)), run_time=0.7)


class Scene5_MemoryEN(EnglishKernelScene):
    scene_key = "Scene5_MemoryEN"
    fallback_duration = 21

    def construct(self):
        self.begin_sync()
        title = self.title("Virtual memory creates private worlds")
        p1 = card("Process A", width=3.2, color=USER, font_size=24).move_to(LEFT * 4.4 + UP * 1.3)
        p2 = card("Process B", width=3.2, color=USER, font_size=24).move_to(LEFT * 4.4 + DOWN * 1.3)
        addr1 = t("0x4000", 28, MEMORY, BOLD).next_to(p1, RIGHT, buff=0.45)
        addr2 = t("0x4000", 28, MEMORY, BOLD).next_to(p2, RIGHT, buff=0.45)
        table = card("page tables", width=3.0, height=1.3, color=KERNEL, font_size=24).move_to(ORIGIN)
        ram = VGroup(
            card("RAM A", width=2.0, height=0.75, color=MEMORY, font_size=20),
            card("RAM B", width=2.0, height=0.75, color=PURPLE, font_size=20),
            card("kernel", width=2.0, height=0.75, color=KERNEL, font_size=20),
        ).arrange(DOWN, buff=0.08).move_to(RIGHT * 4.3)
        self.play(FadeIn(title), FadeIn(p1), FadeIn(p2), Write(addr1), Write(addr2), FadeIn(table), FadeIn(ram), run_time=2)
        arrows = VGroup(
            Arrow(addr1.get_right(), table.get_left() + UP * 0.25, color=USER, buff=0.1),
            Arrow(table.get_right() + UP * 0.25, ram[0].get_left(), color=MEMORY, buff=0.1),
            Arrow(addr2.get_right(), table.get_left() + DOWN * 0.25, color=USER, buff=0.1),
            Arrow(table.get_right() + DOWN * 0.25, ram[1].get_left(), color=PURPLE, buff=0.1),
        )
        self.play(LaggedStart(*[Create(a) for a in arrows], lag_ratio=0.13), run_time=2.2)
        shield = SurroundingRectangle(ram[2], color=KERNEL, buff=0.12, stroke_width=4)
        protected = t("protected", 27, KERNEL, BOLD).next_to(ram[2], DOWN, buff=0.22)
        self.play(Create(shield), Write(protected), run_time=1.5)
        self.finish_sync()
        self.play(FadeOut(VGroup(title, p1, p2, addr1, addr2, table, ram, arrows, shield, protected)), run_time=0.7)


class Scene6_AbstractionsEN(EnglishKernelScene):
    scene_key = "Scene6_AbstractionsEN"
    fallback_duration = 20

    def construct(self):
        self.begin_sync()
        title = self.title("The kernel turns hardware into interfaces")
        app = card("program", width=3.0, color=USER, font_size=25).to_edge(LEFT, buff=0.75)
        kernel = kernel_badge("KERNEL").move_to(ORIGIN).scale(0.95)
        hardware = VGroup(hardware_box("SSD", "IO", width=1.8), hardware_box("NIC", "IP", width=1.8), hardware_box("USB", "DEV", width=1.8)).arrange(DOWN, buff=0.28).move_to(RIGHT * 2.25)
        abstractions = VGroup(
            card("files", width=2.4, color=MEMORY, font_size=23),
            card("sockets", width=2.4, color=PURPLE, font_size=23),
            card("devices", width=2.4, color=KERNEL, font_size=23),
        ).arrange(DOWN, buff=0.28).to_edge(RIGHT, buff=0.8)
        self.play(FadeIn(title), FadeIn(app), FadeIn(kernel, scale=0.7), FadeIn(hardware), FadeIn(abstractions), run_time=2)
        arrows = VGroup(Arrow(app.get_right(), kernel.get_left(), color=USER, buff=0.15))
        for hw, abstraction in zip(hardware, abstractions):
            arrows.add(Arrow(kernel.get_right(), hw.get_left(), color=KERNEL, buff=0.12))
            arrows.add(Arrow(hw.get_right(), abstraction.get_left(), color=MEMORY, buff=0.12))
        self.play(LaggedStart(*[Create(a) for a in arrows], lag_ratio=0.08), run_time=2.3)
        orbit = VGroup(t("drivers", 22, MUTED), t("network", 22, MUTED), t("timers", 22, MUTED), t("IPC", 22, MUTED)).arrange(RIGHT, buff=0.45).to_edge(DOWN, buff=0.75)
        self.play(LaggedStart(*[FadeIn(o, shift=UP * 0.15) for o in orbit], lag_ratio=0.12), Circumscribe(kernel, color=KERNEL), run_time=1.8)
        self.finish_sync()
        self.play(FadeOut(VGroup(title, app, kernel, hardware, abstractions, arrows, orbit)), run_time=0.7)


class Scene7_InterruptsEN(EnglishKernelScene):
    scene_key = "Scene7_InterruptsEN"
    fallback_duration = 28

    def construct(self):
        self.begin_sync()
        title = self.title("The kernel reacts to hardware events")
        cpu = VGroup(Circle(radius=1.0, color=HARDWARE, stroke_width=4).set_fill("#202733", 1), t("CPU", 36, TEXT, BOLD)).move_to(ORIGIN)
        kernel = card("interrupt\nhandler", width=2.65, height=1.25, color=KERNEL, font_size=23).next_to(cpu, DOWN, buff=0.75)
        devices = VGroup(
            hardware_box("NET", "IP", width=1.7),
            hardware_box("KEY", "IO", width=1.7),
            hardware_box("TIMER", "CLK", width=1.7),
            hardware_box("DISK", "IO", width=1.7),
        ).arrange(DOWN, buff=0.2).to_edge(LEFT, buff=0.85)
        sleeping = card("sleeping\nprocess", width=2.7, height=1.05, color=USER, font_size=21).to_edge(RIGHT, buff=0.9)
        event_labels = VGroup(t("packet", 20, MEMORY), t("keypress", 20, USER), t("tick", 20, PURPLE), t("done", 20, DANGER))
        for label, device in zip(event_labels, devices):
            label.next_to(device, RIGHT, buff=0.28)

        self.play(FadeIn(title), FadeIn(devices), FadeIn(cpu, scale=0.75), FadeIn(kernel), FadeIn(sleeping), run_time=2.0)
        pulses = VGroup()
        for device in devices:
            pulses.add(Arrow(device.get_right(), cpu.get_left(), color=DANGER, buff=0.15, stroke_width=3))
        self.play(LaggedStart(*[FadeIn(label, shift=RIGHT * 0.12) for label in event_labels], lag_ratio=0.14), run_time=1.2)
        self.play(LaggedStart(*[Create(pulse) for pulse in pulses], lag_ratio=0.18), Flash(cpu, color=KERNEL, flash_radius=1.4), run_time=2.2)
        jump = Arrow(cpu.get_bottom(), kernel.get_top(), color=KERNEL, buff=0.12, stroke_width=4)
        wake = Arrow(kernel.get_right(), sleeping.get_left(), color=MEMORY, buff=0.16, stroke_width=4)
        self.play(Create(jump), Circumscribe(kernel, color=KERNEL), run_time=1.4)
        state = t("wake up the right process", 28, MEMORY, BOLD).next_to(sleeping, DOWN, buff=0.35)
        self.play(Create(wake), Write(state), sleeping.animate.set_fill("#1B3A38", opacity=1), run_time=1.8)
        self.finish_sync()
        self.play(FadeOut(VGroup(title, devices, event_labels, cpu, kernel, sleeping, pulses, jump, wake, state)), run_time=0.7)


class Scene8_DriversEN(EnglishKernelScene):
    scene_key = "Scene8_DriversEN"
    fallback_duration = 28

    def construct(self):
        self.begin_sync()
        title = self.title("Drivers translate between kernel and devices")
        program = card("program", width=2.5, color=USER, font_size=24).to_edge(LEFT, buff=0.75)
        api = card("stable\ninterface", width=2.55, height=1.15, color=MEMORY, font_size=22).move_to(LEFT * 1.65)
        driver = card("device\ndriver", width=2.55, height=1.15, color=KERNEL, font_size=22).move_to(RIGHT * 1.25)
        devices = VGroup(
            hardware_box("GPU", "PCI", width=1.65),
            hardware_box("NVMe", "IO", width=1.65),
            hardware_box("Wi-Fi", "RF", width=1.65),
        ).arrange(DOWN, buff=0.22).to_edge(RIGHT, buff=0.8)
        self.play(FadeIn(title), FadeIn(program), FadeIn(api), FadeIn(driver), FadeIn(devices), run_time=2.0)
        arrows = VGroup(Arrow(program.get_right(), api.get_left(), color=USER, buff=0.12), Arrow(api.get_right(), driver.get_left(), color=MEMORY, buff=0.12))
        for device in devices:
            arrows.add(Arrow(driver.get_right(), device.get_left(), color=KERNEL, buff=0.12))
        self.play(LaggedStart(*[Create(a) for a in arrows], lag_ratio=0.12), run_time=2.0)
        protocol = VGroup(t("commands", 21, MUTED), t("registers", 21, MUTED), t("DMA", 21, MUTED), t("firmware", 21, MUTED)).arrange(RIGHT, buff=0.35).to_edge(DOWN, buff=0.75)
        warning = t("high privilege, high responsibility", 32, DANGER, BOLD).to_edge(UP, buff=1.25)
        self.play(LaggedStart(*[FadeIn(item, shift=UP * 0.15) for item in protocol], lag_ratio=0.12), run_time=1.5)
        self.play(Write(warning), Circumscribe(driver, color=DANGER), run_time=1.7)
        self.finish_sync()
        self.play(FadeOut(VGroup(title, program, api, driver, devices, arrows, protocol, warning)), run_time=0.7)


class Scene9_ProcessLifecycleEN(EnglishKernelScene):
    scene_key = "Scene9_ProcessLifecycleEN"
    fallback_duration = 30

    def construct(self):
        self.begin_sync()
        title = self.title("Starting a program is kernel bookkeeping")
        terminal = card("shell", width=2.5, color=USER, font_size=25).to_edge(LEFT, buff=0.75)
        fork = card("fork", width=1.65, color=MEMORY, font_size=24).move_to(LEFT * 2.0)
        exec_box = card("exec", width=1.65, color=PURPLE, font_size=24).move_to(ORIGIN)
        process = card("new\nprocess", width=2.35, height=1.05, color=USER, font_size=22).move_to(RIGHT * 2.05)
        cpu = VGroup(Circle(radius=0.72, color=HARDWARE, stroke_width=3).set_fill("#202733", 1), t("CPU", 26, TEXT, BOLD)).to_edge(RIGHT, buff=0.9)
        self.play(FadeIn(title), FadeIn(terminal), FadeIn(fork), FadeIn(exec_box), FadeIn(process), FadeIn(cpu), run_time=1.8)
        flow = VGroup(
            Arrow(terminal.get_right(), fork.get_left(), color=USER, buff=0.12),
            Arrow(fork.get_right(), exec_box.get_left(), color=MEMORY, buff=0.12),
            Arrow(exec_box.get_right(), process.get_left(), color=PURPLE, buff=0.12),
            Arrow(process.get_right(), cpu.get_left(), color=KERNEL, buff=0.12),
        )
        self.play(LaggedStart(*[Create(a) for a in flow], lag_ratio=0.18), run_time=2.2)
        metadata = VGroup(
            card("PID", width=1.45, height=0.6, color=KERNEL, font_size=18),
            card("memory map", width=2.15, height=0.6, color=MEMORY, font_size=18),
            card("file descriptors", width=2.55, height=0.6, color=PURPLE, font_size=18),
            card("priority", width=1.75, height=0.6, color=DANGER, font_size=18),
        ).arrange(RIGHT, buff=0.16).to_edge(DOWN, buff=0.78)
        self.play(LaggedStart(*[FadeIn(item, shift=UP * 0.18) for item in metadata], lag_ratio=0.13), run_time=1.8)
        label = t("launching an app = scheduling + memory + permissions", 31, TEXT, BOLD).to_edge(UP, buff=1.25)
        self.play(Write(label), Circumscribe(process, color=KERNEL), run_time=1.7)
        self.finish_sync()
        self.play(FadeOut(VGroup(title, terminal, fork, exec_box, process, cpu, flow, metadata, label)), run_time=0.7)


class Scene7_ContainersEN(EnglishKernelScene):
    scene_key = "Scene7_ContainersEN"
    fallback_duration = 20

    def construct(self):
        self.begin_sync()
        title = self.title("Containers are kernel isolation")
        kernel = RoundedRectangle(width=10.8, height=1.15, corner_radius=0.15, color=KERNEL, stroke_width=3).set_fill("#2A220B", 1).to_edge(DOWN, buff=0.65)
        kernel_label = t("one Linux kernel", 31, KERNEL, BOLD).move_to(kernel)
        c1 = RoundedRectangle(width=4.3, height=3.0, corner_radius=0.16, color=USER, stroke_width=3).set_fill("#12243E", 0.9).shift(LEFT * 2.55 + UP * 0.8)
        c2 = RoundedRectangle(width=4.3, height=3.0, corner_radius=0.16, color=PURPLE, stroke_width=3).set_fill("#201833", 0.9).shift(RIGHT * 2.55 + UP * 0.8)
        labels = VGroup(t("container A", 29, USER, BOLD).move_to(c1.get_top() + DOWN * 0.45), t("container B", 29, PURPLE, BOLD).move_to(c2.get_top() + DOWN * 0.45))
        proc_a = card("process", width=2.4, height=0.72, color=USER, font_size=20).move_to(c1.get_center() + UP * 0.15)
        proc_b = card("process", width=2.4, height=0.72, color=PURPLE, font_size=20).move_to(c2.get_center() + UP * 0.15)
        ns = card("namespaces\nwhat it sees", width=3.3, height=1.0, color=MEMORY, font_size=20).move_to(c1.get_bottom() + UP * 0.65)
        cg = card("cgroups\nwhat it consumes", width=3.3, height=1.0, color=DANGER, font_size=20).move_to(c2.get_bottom() + UP * 0.65)
        self.play(FadeIn(title), FadeIn(VGroup(c1, c2, labels, proc_a, proc_b)), FadeIn(VGroup(kernel, kernel_label), shift=UP * 0.2), run_time=2)
        self.play(Create(Arrow(proc_a.get_bottom(), kernel.get_top() + LEFT * 2.55, color=USER, buff=0.1)), Create(Arrow(proc_b.get_bottom(), kernel.get_top() + RIGHT * 2.55, color=PURPLE, buff=0.1)), run_time=1.3)
        self.play(FadeIn(ns, shift=UP * 0.2), FadeIn(cg, shift=UP * 0.2), run_time=1.5)
        self.play(Circumscribe(ns, color=MEMORY), Circumscribe(cg, color=DANGER), run_time=1.5)
        self.finish_sync()
        self.play(FadeOut(VGroup(title, c1, c2, labels, proc_a, proc_b, ns, cg, kernel, kernel_label)), run_time=0.7)


class Scene10_WhatKernelIsNotEN(EnglishKernelScene):
    scene_key = "Scene10_WhatKernelIsNotEN"
    fallback_duration = 28

    def construct(self):
        self.begin_sync()
        title = self.title("The kernel is not the whole operating system")
        kernel = kernel_badge("Linux\nkernel").scale(0.86).move_to(ORIGIN + DOWN * 0.35)
        user_space = VGroup(
            card("shell", width=1.75, height=0.65, color=USER, font_size=19),
            card("desktop", width=1.95, height=0.65, color=PURPLE, font_size=19),
            card("package\nmanager", width=2.2, height=0.85, color=MEMORY, font_size=18),
            card("system\nservices", width=2.2, height=0.85, color=DANGER, font_size=18),
        ).arrange(RIGHT, buff=0.18).to_edge(UP, buff=1.45)
        distros = VGroup(
            card("Ubuntu", width=1.7, height=0.62, color=USER, font_size=18),
            card("Arch", width=1.45, height=0.62, color=MEMORY, font_size=18),
            card("Fedora", width=1.65, height=0.62, color=PURPLE, font_size=18),
            card("Android", width=1.85, height=0.62, color=KERNEL, font_size=18),
        ).arrange(RIGHT, buff=0.18).to_edge(DOWN, buff=0.8)
        shell = RoundedRectangle(width=10.9, height=4.3, corner_radius=0.18, color="#2D3646", stroke_width=2).move_to(ORIGIN)
        label_top = t("user space tools and policies", 24, MUTED).next_to(user_space, DOWN, buff=0.25)
        label_bottom = t("complete systems built around the kernel", 24, MUTED).next_to(distros, UP, buff=0.25)
        self.play(FadeIn(title), Create(shell), FadeIn(kernel, scale=0.75), run_time=1.7)
        self.play(LaggedStart(*[FadeIn(item, shift=DOWN * 0.18) for item in user_space], lag_ratio=0.11), Write(label_top), run_time=1.8)
        links = VGroup(*[Arrow(item.get_bottom(), kernel.get_top(), color=MUTED, buff=0.12, stroke_width=2.4) for item in user_space])
        self.play(LaggedStart(*[Create(link) for link in links], lag_ratio=0.08), run_time=1.4)
        self.play(LaggedStart(*[FadeIn(item, shift=UP * 0.18) for item in distros], lag_ratio=0.11), Write(label_bottom), run_time=1.8)
        distinction = t("Linux can mean the kernel, or a full system.", 34, TEXT, BOLD).to_edge(LEFT, buff=0.95).shift(DOWN * 0.15)
        self.play(Write(distinction), Circumscribe(kernel, color=KERNEL), run_time=1.8)
        self.finish_sync()
        self.play(FadeOut(VGroup(title, shell, kernel, user_space, distros, label_top, label_bottom, links, distinction)), run_time=0.7)


class Scene8_RecapEN(EnglishKernelScene):
    scene_key = "Scene8_RecapEN"
    fallback_duration = 22

    def construct(self):
        self.begin_sync()
        kernel = kernel_badge("KERNEL").scale(1.05).move_to(ORIGIN + UP * 0.25)
        verbs = VGroup(
            card("protects", width=2.6, color=DANGER, font_size=25),
            card("shares", width=2.6, color=USER, font_size=25),
            card("abstracts", width=2.6, color=MEMORY, font_size=25),
        ).arrange(RIGHT, buff=0.38).to_edge(DOWN, buff=1.0)
        self.play(FadeIn(kernel, scale=0.7), LaggedStart(*[FadeIn(v, shift=UP * 0.25) for v in verbs], lag_ratio=0.2), run_time=2.4)
        layers = VGroup(t("applications", 26, USER, BOLD), t("syscalls", 24, TEXT), t("Linux kernel", 30, KERNEL, BOLD), t("CPU  RAM  disk  network", 24, HARDWARE)).arrange(DOWN, buff=0.35).to_edge(LEFT, buff=0.8)
        arrows = VGroup(*[Arrow(a.get_bottom(), b.get_top(), color=MUTED, buff=0.08, max_tip_length_to_length_ratio=0.12) for a, b in zip(layers[:-1], layers[1:])])
        self.play(FadeOut(kernel), FadeIn(layers), LaggedStart(*[Create(a) for a in arrows], lag_ratio=0.12), run_time=2.6)
        final = t("raw hardware becomes a usable system", 40, TEXT, BOLD).to_edge(UP, buff=0.75)
        next_video = t("Next: what is a syscall?", 30, KERNEL).to_edge(DOWN, buff=0.42)
        self.play(Write(final), Write(next_video), run_time=2.0)
        self.finish_sync()
        self.play(FadeOut(VGroup(verbs, layers, arrows, final, next_video)), run_time=0.7)
