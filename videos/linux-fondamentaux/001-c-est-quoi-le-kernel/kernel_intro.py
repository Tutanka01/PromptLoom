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


def scene_caption(scene, text, duration):
    scene.add_subcaption(text, duration=duration)


class KernelVideoScene(Scene):
    def setup(self):
        self.camera.background_color = BG

    def title(self, text):
        label = t(text, 34, TEXT, BOLD).to_edge(UP, buff=0.35)
        line = Line(LEFT * 6.2, RIGHT * 6.2, color="#2D3646", stroke_width=2).next_to(label, DOWN, buff=0.18)
        return VGroup(label, line)


class Scene1_Hook(KernelVideoScene):
    def construct(self):
        scene_caption(
            self,
            "Imagine que tu ouvres une application et que tu lui demandes de lire un fichier.",
            7,
        )
        app = card("Application", width=3.8, height=1.25, color=USER, font_size=32)
        request = t('ouvrir "photo.png"', 30, TEXT).next_to(app, DOWN, buff=0.45)
        cursor = Triangle(color=KERNEL, fill_opacity=1).scale(0.16).rotate(-PI / 2)
        cursor.next_to(request, LEFT, buff=0.18)

        self.play(FadeIn(app, shift=UP * 0.25), Write(request), FadeIn(cursor), run_time=2)
        self.wait(6)

        scene_caption(
            self,
            "Ton programme ne parle pas directement au disque, au processeur ou à la mémoire.",
            7,
        )
        layers = VGroup(
            card("user space", width=5.0, height=0.8, color=USER, font_size=25),
            card("kernel", width=5.0, height=0.8, color=KERNEL, font_size=25),
            card("matériel", width=5.0, height=0.8, color=HARDWARE, font_size=25),
        ).arrange(DOWN, buff=0.14)
        layers.move_to(ORIGIN)

        self.play(
            ReplacementTransform(app, layers[0]),
            ReplacementTransform(request, layers[1]),
            cursor.animate.move_to(layers[2].get_left() + LEFT * 0.35),
            run_time=2.2,
        )
        self.play(FadeIn(layers[2], shift=DOWN * 0.2), run_time=1)

        scene_caption(
            self,
            "Entre ton application et la machine réelle, il y a une couche invisible : le kernel.",
            7,
        )
        glow = SurroundingRectangle(layers[1], color=KERNEL, buff=0.12, stroke_width=4)
        question = t("Qui contrôle vraiment la machine ?", 42, TEXT, BOLD).to_edge(DOWN, buff=0.7)
        self.play(Create(glow), Write(question), run_time=2)
        self.wait(21)
        self.play(FadeOut(VGroup(layers, glow, question, cursor)), run_time=1)


class Scene2_HardwareChaos(KernelVideoScene):
    def construct(self):
        title = self.title("Sans kernel : chaque programme fonce vers le matériel")
        scene_caption(
            self,
            "Le matériel est puissant, mais brutal. Sans arbitre, chaque programme devrait tout piloter lui-même.",
            8,
        )
        apps = VGroup(
            card("navigateur", color=USER, font_size=22),
            card("terminal", color=USER, font_size=22),
            card("musique", color=USER, font_size=22),
        ).arrange(DOWN, buff=0.25).to_edge(LEFT, buff=0.8)
        hw = VGroup(
            hardware_box("CPU", "▦"),
            hardware_box("RAM", "▤"),
            hardware_box("DISQUE", "◉"),
            hardware_box("RÉSEAU", "⌁"),
        ).arrange(DOWN, buff=0.18).to_edge(RIGHT, buff=0.75)
        arrows = VGroup()
        for app in apps:
            for device in hw:
                arrows.add(
                    Arrow(app.get_right(), device.get_left(), buff=0.12, color=DANGER, stroke_width=2.3, max_tip_length_to_length_ratio=0.06)
                )

        self.play(FadeIn(title), LaggedStart(*[FadeIn(a, shift=RIGHT * 0.2) for a in apps], lag_ratio=0.12), run_time=2)
        self.play(LaggedStart(*[FadeIn(h, shift=LEFT * 0.2) for h in hw], lag_ratio=0.1), run_time=1.4)
        self.play(LaggedStart(*[Create(a) for a in arrows], lag_ratio=0.02), run_time=3)

        scene_caption(
            self,
            "Un programme pourrait lire les données d'un autre, écraser la mémoire, ou monopoliser le CPU.",
            8,
        )
        warning = t("rapide, mais dangereux", 40, DANGER, BOLD).to_edge(DOWN, buff=0.55)
        self.play(Write(warning), Circumscribe(arrows, color=DANGER), run_time=2)
        self.wait(8)

        scene_caption(
            self,
            "Le kernel apparaît comme l'arbitre qui impose des règles communes.",
            6,
        )
        kernel = kernel_badge().move_to(ORIGIN)
        clean_arrows = VGroup(
            *[Arrow(app.get_right(), kernel.get_left(), buff=0.15, color=USER, stroke_width=3) for app in apps],
            *[Arrow(kernel.get_right(), device.get_left(), buff=0.15, color=KERNEL, stroke_width=3) for device in hw],
        )
        self.play(FadeOut(arrows), FadeOut(warning), FadeIn(kernel, scale=0.7), run_time=1.8)
        self.play(LaggedStart(*[Create(a) for a in clean_arrows], lag_ratio=0.06), run_time=2.3)
        self.wait(18.5)
        self.play(FadeOut(VGroup(title, apps, hw, kernel, clean_arrows)), run_time=1)


class Scene3_UserKernelBoundary(KernelVideoScene):
    def construct(self):
        title = self.title("La frontière : user space / kernel space")
        scene_caption(
            self,
            "Les applications vivent en user space. Le kernel vit dans une zone protégée : le kernel space.",
            8,
        )
        top = Rectangle(width=12.5, height=2.5, color=USER, stroke_width=2).set_fill("#12243E", opacity=0.7).shift(UP * 1.45)
        bottom = Rectangle(width=12.5, height=2.5, color=KERNEL, stroke_width=2).set_fill("#322808", opacity=0.7).shift(DOWN * 1.45)
        labels = VGroup(
            t("USER SPACE", 30, USER, BOLD).move_to(top.get_left() + RIGHT * 1.45 + UP * 0.85),
            t("KERNEL SPACE", 30, KERNEL, BOLD).move_to(bottom.get_left() + RIGHT * 1.65 + DOWN * 0.85),
        )
        boundary = DashedLine(LEFT * 6.2, RIGHT * 6.2, color=TEXT, stroke_width=3)
        app = card("processus", color=USER, font_size=24).move_to(UP * 1.45 + LEFT * 3.8)
        kernel = kernel_badge("NOYAU").scale(0.8).move_to(DOWN * 1.45 + RIGHT * 3.7)
        gate = RoundedRectangle(width=1.2, height=1.1, corner_radius=0.08, color=KERNEL, stroke_width=3).set_fill("#2A220B", 1)
        gate_label = t("syscall", 20, KERNEL, BOLD).move_to(gate)
        gate_group = VGroup(gate, gate_label).move_to(ORIGIN)

        self.play(FadeIn(title), FadeIn(top), FadeIn(bottom), Write(labels), Create(boundary), run_time=2)
        self.play(FadeIn(app), FadeIn(kernel), FadeIn(gate_group), run_time=1.5)
        self.wait(8)

        scene_caption(
            self,
            "Une syscall est une demande officielle au kernel, pas un accès direct au matériel.",
            8,
        )
        open_call = t("open(\"photo.png\")", 30, TEXT).next_to(app, DOWN, buff=0.28)
        arrow1 = Arrow(app.get_bottom(), gate_group.get_top(), color=USER, buff=0.1)
        arrow2 = Arrow(gate_group.get_bottom(), kernel.get_left(), color=KERNEL, buff=0.1)
        response = Arrow(kernel.get_top(), app.get_right(), color=MEMORY, buff=0.1)
        ok = t("fd = 3", 26, MEMORY, BOLD).next_to(response, RIGHT, buff=0.1)
        self.play(Write(open_call), Create(arrow1), run_time=1.5)
        self.play(Circumscribe(gate_group, color=KERNEL), Create(arrow2), run_time=1.7)
        self.play(Create(response), FadeIn(ok), run_time=1.5)
        self.wait(10)

        scene_caption(
            self,
            "Le kernel vérifie les permissions, consulte le système de fichiers, puis répond.",
            7,
        )
        checks = VGroup(
            t("permissions", 22, TEXT),
            t("filesystem", 22, TEXT),
            t("driver", 22, TEXT),
        ).arrange(RIGHT, buff=0.45).next_to(kernel, DOWN, buff=0.5)
        for item in checks:
            item.add(SurroundingRectangle(item, color=KERNEL, buff=0.15))
        self.play(LaggedStart(*[FadeIn(item, shift=UP * 0.2) for item in checks], lag_ratio=0.2), run_time=2)
        self.wait(25)
        self.play(FadeOut(VGroup(title, top, bottom, labels, boundary, app, kernel, gate_group, open_call, arrow1, arrow2, response, ok, checks)), run_time=1)


class Scene4_Scheduler(KernelVideoScene):
    def construct(self):
        title = self.title("Le scheduler : partager le CPU")
        scene_caption(
            self,
            "À un instant précis, un coeur de CPU exécute une suite d'instructions. Pourtant, tout semble tourner en même temps.",
            8,
        )
        processes = VGroup(
            card("P1 navigateur", color=USER, font_size=21),
            card("P2 terminal", color=USER, font_size=21),
            card("P3 musique", color=USER, font_size=21),
            card("P4 serveur", color=USER, font_size=21),
        ).arrange(DOWN, buff=0.2).to_edge(LEFT, buff=0.7)
        cpu = Circle(radius=1.15, color=HARDWARE, stroke_width=4).set_fill("#202733", 1).move_to(RIGHT * 3.55)
        cpu_label = t("CPU", 40, TEXT, BOLD).move_to(cpu)
        scheduler = card("scheduler", width=3.1, height=0.85, color=KERNEL, font_size=25).move_to(ORIGIN + DOWN * 0.05)
        queue_arrow = Arrow(processes.get_right(), scheduler.get_left(), color=USER, buff=0.18)
        cpu_arrow = Arrow(scheduler.get_right(), cpu.get_left(), color=KERNEL, buff=0.18)

        self.play(FadeIn(title), FadeIn(processes, shift=RIGHT * 0.2), FadeIn(VGroup(cpu, cpu_label)), run_time=2)
        self.play(FadeIn(scheduler), Create(queue_arrow), Create(cpu_arrow), run_time=1.5)

        scene_caption(
            self,
            "Le scheduler donne le CPU à un processus, puis à un autre, souvent pour quelques millisecondes.",
            9,
        )
        slots = VGroup()
        colors = [USER, MEMORY, PURPLE, DANGER, USER, MEMORY]
        names = ["P1", "P2", "P3", "P1", "P4", "P2"]
        for name, color in zip(names, colors):
            slots.add(Rectangle(width=1.05, height=0.55, color=color, stroke_width=2).set_fill(color, 0.3))
            slots[-1].add(t(name, 20, TEXT, BOLD).move_to(slots[-1]))
        slots.arrange(RIGHT, buff=0.05).to_edge(DOWN, buff=0.75)
        timeline = t("temps CPU découpé", 24, MUTED).next_to(slots, UP, buff=0.22)
        self.play(Write(timeline), LaggedStart(*[FadeIn(slot, shift=UP * 0.15) for slot in slots], lag_ratio=0.15), run_time=3)
        self.wait(9)

        highlights = []
        for i, proc in enumerate([processes[0], processes[1], processes[2], processes[0], processes[3], processes[1]]):
            h = SurroundingRectangle(proc, color=colors[i], buff=0.08, stroke_width=3)
            highlights.append(h)
            self.play(Create(h), slots[i].animate.set_fill(colors[i], opacity=0.75), run_time=0.45)
            self.play(TransformFromCopy(proc, cpu_label), run_time=0.35)
            self.remove(h)

        scene_caption(
            self,
            "Le multitâche est donc une illusion très rapide, orchestrée par le kernel.",
            6,
        )
        insight = t("multitâche = arbitrage rapide", 36, KERNEL, BOLD).next_to(cpu, DOWN, buff=0.6)
        self.play(Write(insight), Circumscribe(scheduler, color=KERNEL), run_time=2)
        self.wait(11)
        self.play(FadeOut(VGroup(title, processes, cpu, cpu_label, scheduler, queue_arrow, cpu_arrow, slots, timeline, insight)), run_time=1)


class Scene5_VirtualMemory(KernelVideoScene):
    def construct(self):
        title = self.title("Mémoire virtuelle : chaque processus voit son monde")
        scene_caption(
            self,
            "Chaque programme a l'impression d'avoir une mémoire propre, continue et privée.",
            7,
        )
        p1 = card("Processus A", width=3.2, color=USER, font_size=24).move_to(LEFT * 4.4 + UP * 1.3)
        p2 = card("Processus B", width=3.2, color=USER, font_size=24).move_to(LEFT * 4.4 + DOWN * 1.3)
        addr1 = t("0x4000", 28, MEMORY, BOLD).next_to(p1, RIGHT, buff=0.45)
        addr2 = t("0x4000", 28, MEMORY, BOLD).next_to(p2, RIGHT, buff=0.45)
        table = card("tables de pages", width=3.0, height=1.3, color=KERNEL, font_size=24).move_to(ORIGIN)
        ram = VGroup(
            Rectangle(width=2.0, height=0.75, color=MEMORY).set_fill("#0F3A31", 1),
            Rectangle(width=2.0, height=0.75, color=PURPLE).set_fill("#291E3C", 1),
            Rectangle(width=2.0, height=0.75, color=HARDWARE).set_fill("#202733", 1),
        ).arrange(DOWN, buff=0.08).move_to(RIGHT * 4.3)
        ram_labels = VGroup(
            t("RAM A", 21, TEXT),
            t("RAM B", 21, TEXT),
            t("kernel", 21, KERNEL),
        )
        for label, block in zip(ram_labels, ram):
            label.move_to(block)
        ram_group = VGroup(ram, ram_labels)

        self.play(FadeIn(title), FadeIn(p1), FadeIn(p2), Write(addr1), Write(addr2), run_time=2)
        self.play(FadeIn(table), FadeIn(ram_group), run_time=1.5)

        scene_caption(
            self,
            "Deux processus peuvent voir la même adresse virtuelle, mais arriver à deux endroits physiques différents.",
            8,
        )
        arrows = VGroup(
            Arrow(addr1.get_right(), table.get_left() + UP * 0.25, color=USER, buff=0.1),
            Arrow(table.get_right() + UP * 0.25, ram[0].get_left(), color=MEMORY, buff=0.1),
            Arrow(addr2.get_right(), table.get_left() + DOWN * 0.25, color=USER, buff=0.1),
            Arrow(table.get_right() + DOWN * 0.25, ram[1].get_left(), color=PURPLE, buff=0.1),
        )
        self.play(LaggedStart(*[Create(a) for a in arrows], lag_ratio=0.15), run_time=3)
        self.wait(10)

        scene_caption(
            self,
            "Le kernel protège les zones sensibles pour qu'un bug ne devienne pas une catastrophe globale.",
            8,
        )
        shield = SurroundingRectangle(ram[2], color=KERNEL, buff=0.12, stroke_width=4)
        lock = t("protégé", 28, KERNEL, BOLD).next_to(ram[2], RIGHT, buff=0.35)
        self.play(Create(shield), Write(lock), run_time=1.8)
        self.wait(18)
        self.play(FadeOut(VGroup(title, p1, p2, addr1, addr2, table, ram_group, arrows, shield, lock)), run_time=1)


class Scene6_FilesNetworkDrivers(KernelVideoScene):
    def construct(self):
        title = self.title("Le kernel transforme le chaos en abstractions")
        scene_caption(
            self,
            "Le kernel donne aux programmes des interfaces stables : fichiers, sockets, périphériques.",
            8,
        )
        kernel = kernel_badge("KERNEL").move_to(ORIGIN).scale(0.95)
        app = card("programme", width=3.0, color=USER, font_size=25).to_edge(LEFT, buff=0.75)
        abstractions = VGroup(
            card("fichiers", width=2.4, color=MEMORY, font_size=23),
            card("sockets", width=2.4, color=PURPLE, font_size=23),
            card("devices", width=2.4, color=KERNEL, font_size=23),
        ).arrange(DOWN, buff=0.28).to_edge(RIGHT, buff=0.8)
        hardware = VGroup(
            hardware_box("SSD", "◉", width=1.8),
            hardware_box("NIC", "⌁", width=1.8),
            hardware_box("USB", "▣", width=1.8),
        ).arrange(DOWN, buff=0.28).next_to(abstractions, LEFT, buff=0.55)

        self.play(FadeIn(title), FadeIn(app), FadeIn(kernel, scale=0.7), run_time=1.8)
        self.play(Create(Arrow(app.get_right(), kernel.get_left(), color=USER, buff=0.15)), run_time=1)
        self.play(LaggedStart(*[FadeIn(h, shift=LEFT * 0.2) for h in hardware], lag_ratio=0.14), run_time=1.8)
        self.play(LaggedStart(*[FadeIn(a, shift=LEFT * 0.2) for a in abstractions], lag_ratio=0.14), run_time=1.8)
        self.wait(9)

        scene_caption(
            self,
            "Un SSD, une clé USB ou un système de fichiers réseau peuvent devenir une même idée : un fichier.",
            8,
        )
        arrows = VGroup()
        for hw, abstraction in zip(hardware, abstractions):
            arrows.add(Arrow(kernel.get_right(), hw.get_left(), color=KERNEL, buff=0.12))
            arrows.add(Arrow(hw.get_right(), abstraction.get_left(), color=MEMORY, buff=0.12))
        self.play(LaggedStart(*[Create(a) for a in arrows], lag_ratio=0.08), run_time=2.4)

        scene_caption(
            self,
            "Drivers, réseau, systèmes de fichiers, signaux et timers tournent autour de cette mission.",
            7,
        )
        orbit = VGroup(
            t("drivers", 21, MUTED).move_to(UP * 2.0),
            t("réseau", 21, MUTED).move_to(DOWN * 2.0),
            t("timers", 21, MUTED).move_to(LEFT * 1.9),
            t("IPC", 21, MUTED).move_to(RIGHT * 1.9),
        )
        self.play(LaggedStart(*[FadeIn(o) for o in orbit], lag_ratio=0.15), Circumscribe(kernel, color=KERNEL), run_time=2.5)
        self.wait(17)
        self.play(FadeOut(VGroup(title, kernel, app, abstractions, hardware, arrows, orbit)), run_time=1)


class Scene7_Containers(KernelVideoScene):
    def construct(self):
        title = self.title("Containers : pas un mini-kernel, une isolation du kernel")
        scene_caption(
            self,
            "Quand tu lances un container Docker, tu ne démarres pas un nouveau petit kernel complet.",
            8,
        )
        kernel = RoundedRectangle(width=10.8, height=1.15, corner_radius=0.15, color=KERNEL, stroke_width=3).set_fill("#2A220B", 1).to_edge(DOWN, buff=0.65)
        kernel_label = t("un seul kernel Linux", 31, KERNEL, BOLD).move_to(kernel)
        c1 = RoundedRectangle(width=4.3, height=3.0, corner_radius=0.16, color=USER, stroke_width=3).set_fill("#12243E", 0.9).shift(LEFT * 2.55 + UP * 0.8)
        c2 = RoundedRectangle(width=4.3, height=3.0, corner_radius=0.16, color=PURPLE, stroke_width=3).set_fill("#201833", 0.9).shift(RIGHT * 2.55 + UP * 0.8)
        c1_label = t("container A", 28, USER, BOLD).move_to(c1.get_top() + DOWN * 0.45)
        c2_label = t("container B", 28, PURPLE, BOLD).move_to(c2.get_top() + DOWN * 0.45)
        proc_a = card("processus", width=2.4, height=0.72, color=USER, font_size=20).move_to(c1.get_center() + UP * 0.15)
        proc_b = card("processus", width=2.4, height=0.72, color=PURPLE, font_size=20).move_to(c2.get_center() + UP * 0.15)

        self.play(FadeIn(title), FadeIn(VGroup(c1, c2, c1_label, c2_label, proc_a, proc_b)), run_time=2)
        self.play(FadeIn(VGroup(kernel, kernel_label), shift=UP * 0.2), run_time=1.4)
        self.play(
            Create(Arrow(proc_a.get_bottom(), kernel.get_top() + LEFT * 2.55, color=USER, buff=0.1)),
            Create(Arrow(proc_b.get_bottom(), kernel.get_top() + RIGHT * 2.55, color=PURPLE, buff=0.1)),
            run_time=1.5,
        )
        self.wait(8)

        scene_caption(
            self,
            "Les namespaces contrôlent ce que les processus voient. Les cgroups contrôlent ce qu'ils consomment.",
            9,
        )
        ns = card("namespaces\nce qu'on voit", width=3.3, height=1.0, color=MEMORY, font_size=20).move_to(c1.get_bottom() + UP * 0.65)
        cg = card("cgroups\nce qu'on consomme", width=3.3, height=1.0, color=DANGER, font_size=20).move_to(c2.get_bottom() + UP * 0.65)
        self.play(FadeIn(ns, shift=UP * 0.2), FadeIn(cg, shift=UP * 0.2), run_time=1.8)
        self.play(Circumscribe(ns, color=MEMORY), run_time=1.2)
        self.play(Circumscribe(cg, color=DANGER), run_time=1.2)

        scene_caption(
            self,
            "Un container est une configuration intelligente des mécanismes d'isolation du kernel.",
            7,
        )
        insight = t("containers = isolation configurée", 38, KERNEL, BOLD).to_edge(UP, buff=1.0)
        self.play(Write(insight), Circumscribe(kernel, color=KERNEL), run_time=2.2)
        self.wait(20)
        self.play(FadeOut(VGroup(title, kernel, kernel_label, c1, c2, c1_label, c2_label, proc_a, proc_b, ns, cg, insight)), run_time=1)


class Scene8_Recap(KernelVideoScene):
    def construct(self):
        scene_caption(
            self,
            "Si tu dois retenir une phrase : le kernel protège, partage et abstrait le matériel.",
            8,
        )
        kernel = kernel_badge("KERNEL").scale(1.05).move_to(ORIGIN + UP * 0.25)
        verbs = VGroup(
            card("protéger", width=2.6, color=DANGER, font_size=25),
            card("partager", width=2.6, color=USER, font_size=25),
            card("abstraire", width=2.6, color=MEMORY, font_size=25),
        ).arrange(RIGHT, buff=0.38).to_edge(DOWN, buff=1.0)
        self.play(FadeIn(kernel, scale=0.7), run_time=1.5)
        self.play(LaggedStart(*[FadeIn(v, shift=UP * 0.25) for v in verbs], lag_ratio=0.25), run_time=2.5)
        self.wait(10)

        scene_caption(
            self,
            "Il impose des frontières, arbitre les ressources, et transforme le matériel en interfaces simples.",
            8,
        )
        layers = VGroup(
            t("applications", 26, USER, BOLD),
            t("syscalls", 24, TEXT),
            t("kernel Linux", 30, KERNEL, BOLD),
            t("CPU  RAM  disque  réseau", 24, HARDWARE),
        ).arrange(DOWN, buff=0.35).to_edge(LEFT, buff=0.8)
        arrows = VGroup()
        for a, b in zip(layers[:-1], layers[1:]):
            arrows.add(Arrow(a.get_bottom(), b.get_top(), color=MUTED, buff=0.08, max_tip_length_to_length_ratio=0.12))
        self.play(FadeOut(kernel), FadeIn(layers), LaggedStart(*[Create(a) for a in arrows], lag_ratio=0.12), run_time=3)
        self.wait(10)

        scene_caption(
            self,
            "Derrière chaque fichier lu, chaque processus lancé et chaque paquet réseau, il y a le kernel qui décide.",
            8,
        )
        final = t("la machine réelle devient utilisable", 40, TEXT, BOLD).to_edge(UP, buff=0.75)
        next_video = t("Prochaine vidéo : qu'est-ce qu'une syscall ?", 28, KERNEL).to_edge(DOWN, buff=0.42)
        self.play(Write(final), run_time=1.6)
        self.play(Write(next_video), run_time=1.5)
        self.wait(20)
        self.play(FadeOut(VGroup(verbs, layers, arrows, final, next_video)), run_time=1)
