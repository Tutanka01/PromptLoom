from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import ValidationError

from video_api.config import Settings
from video_api.schemas import BeatSpec, SceneSpec, VideoBlueprint


logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You produce educational Linux and low-level systems videos.
Return only valid JSON. The JSON must describe a complete 3-5 minute video blueprint by default.
Every scene must have a key like Scene1_HookEN, Scene2_CoreIdeaEN.
For a 3-5 minute target, produce 8 to 12 scenes with enough narration to actually fill the duration.
Each scene must include duration_seconds, one approved layout, narration text, and 5 to 7 concrete beats unless the scene is very short.
Beat at values must be normalized ratios between 0.0 and 1.0 inside that scene, not seconds or global timestamps.
The voice and image must explain the same idea at the same time.
Do not request raw Python Manim. Plan with this deterministic visual grammar only:
process_pipeline, privilege_boundary, memory_translation, scheduler_timeline, syscall_gate,
cpu_registers, hardware_path, recap_map.
Good Manim scenes use explicit Mobjects, stable positioning, transforms, movement, focus/dim,
and one active idea at a time. Avoid generic "make it nice" visual actions."""


LAYOUTS = [
    "process_pipeline",
    "privilege_boundary",
    "memory_translation",
    "scheduler_timeline",
    "syscall_gate",
    "cpu_registers",
    "hardware_path",
    "recap_map",
]


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("LLM response did not contain a JSON object")
    return json.loads(cleaned[start : end + 1])


def _load_generation_guidelines(settings: Settings) -> str:
    path = settings.repo_root / "apps" / "video-api" / "docs" / "manim-generation-guidelines.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")[:4000]


def _beat_ratio(index: int, count: int) -> float:
    return round(0.12 + (0.76 * index / max(1, count - 1)), 3)


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_absolute_beat_times(beats: list[Any]) -> list[Any]:
    numeric_times = [_float_or_none(beat.get("at")) if isinstance(beat, dict) else None for beat in beats]
    if not any(value is not None and value > 1.0 for value in numeric_times):
        return beats

    known_times = [value for value in numeric_times if value is not None]
    if not known_times:
        return beats

    start = min(known_times)
    end = max(known_times)
    normalized = []
    for beat_index, beat in enumerate(beats):
        if not isinstance(beat, dict):
            normalized.append(beat)
            continue
        beat_item = dict(beat)
        value = numeric_times[beat_index]
        if value is None or end <= start:
            beat_item["at"] = _beat_ratio(beat_index, len(beats))
        else:
            beat_item["at"] = round(0.12 + (0.76 * (value - start) / (end - start)), 3)
        normalized.append(beat_item)
    return normalized


def _coerce_blueprint_shape(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    coerced = dict(data)
    coerced["target_duration_seconds"] = coerced.get("target_duration_seconds") or coerced.get("duration_seconds") or 240
    scenes = coerced.get("scenes")
    if not isinstance(scenes, list):
        return coerced

    normalized_scenes = []
    target_duration = int(coerced.get("target_duration_seconds") or 240)
    default_scene_duration = max(18, round(target_duration / max(1, len(scenes))))
    for scene_index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            normalized_scenes.append(scene)
            continue
        item = dict(scene)
        item["key"] = item.get("key") or item.get("class") or f"Scene{scene_index}_GeneratedEN"
        item["title"] = item.get("title") or item.get("name") or f"Scene {scene_index}"
        item["text"] = (
            item.get("text")
            or item.get("narration")
            or item.get("voiceover")
            or item.get("script")
            or item.get("spoken_text")
        )
        item["visual_intent"] = (
            item.get("visual_intent")
            or item.get("visual_plan")
            or item.get("visual_description")
            or item.get("visual")
            or item.get("description")
        )
        layout = item.get("layout") or item.get("visual_layout") or item.get("template") or item.get("scene_type")
        item["layout"] = layout if layout in LAYOUTS else LAYOUTS[(scene_index - 1) % len(LAYOUTS)]
        item["duration_seconds"] = item.get("duration_seconds") or item.get("target_duration_seconds") or default_scene_duration

        beats = item.get("beats") or item.get("visual_beats") or item.get("beat_sync") or []
        normalized_beats = []
        if isinstance(beats, list):
            count = max(1, len(beats))
            for beat_index, beat in enumerate(beats):
                if not isinstance(beat, dict):
                    normalized_beats.append(beat)
                    continue
                beat_item = dict(beat)
                beat_item["key"] = beat_item.get("key") or f"beat_{beat_index + 1}"
                beat_item["at"] = beat_item.get("at", beat_item.get("time", beat_item.get("ratio")))
                if beat_item["at"] is None:
                    beat_item["at"] = _beat_ratio(beat_index, count)
                beat_item["text_hint"] = (
                    beat_item.get("text_hint")
                    or beat_item.get("spoken_idea")
                    or beat_item.get("narration_hint")
                    or beat_item.get("voiceover")
                    or beat_item.get("text")
                )
                beat_item["visual_action"] = (
                    beat_item.get("visual_action")
                    or beat_item.get("visual")
                    or beat_item.get("action")
                    or beat_item.get("animation")
                    or beat_item.get("screen")
                )
                normalized_beats.append(beat_item)
        item["beats"] = _normalize_absolute_beat_times(normalized_beats)
        normalized_scenes.append(item)
    coerced["scenes"] = normalized_scenes
    return coerced


def fake_blueprint(
    prompt: str,
    theme: str | None = None,
    target_duration_seconds: int | None = None,
) -> VideoBlueprint:
    safe_theme = theme or "linux-fondamentaux"
    target = int(target_duration_seconds or 240)
    title = "Prompt To Kernel Video"
    scene_duration = max(24, round(target / 8))
    scenes = [
        SceneSpec(
            key="Scene1_HookEN",
            title="The visible command",
            duration_seconds=scene_duration,
            layout="process_pipeline",
            text=(
                "A Linux command looks simple from the outside. You type one line, press enter, "
                "and a result appears. But the interesting part is the controlled path between "
                "the program, the kernel, and the hardware. The terminal hides that path, so the "
                "first useful mental model is not the command itself, but the chain of controlled "
                "steps that Linux follows underneath."
            ),
            visual_intent="Show a terminal command, then reveal the kernel path behind it.",
            beats=[
                BeatSpec(key="command", at=0.10, text_hint="A Linux command looks simple", visual_action="Show a terminal command."),
                BeatSpec(key="program", at=0.28, text_hint="from the outside", visual_action="Reveal the user program."),
                BeatSpec(key="hidden_path", at=0.46, text_hint="controlled path", visual_action="Open a path behind the command."),
                BeatSpec(key="kernel", at=0.66, text_hint="program, kernel", visual_action="Connect the program to the kernel."),
                BeatSpec(key="hardware", at=0.86, text_hint="and the hardware", visual_action="Complete the path to hardware."),
            ],
        ),
        SceneSpec(
            key="Scene2_MechanismEN",
            title="The kernel boundary",
            duration_seconds=scene_duration,
            layout="privilege_boundary",
            text=(
                "The kernel is not just another library. It runs with privileges user programs do "
                "not have. That boundary is what lets Linux share the machine without letting one "
                "program overwrite everything else. A browser, shell, and editor can all run at "
                "the same time because each one must cross a guarded boundary before touching "
                "protected resources."
            ),
            visual_intent="Contrast user space with kernel space and show the privilege boundary.",
            beats=[
                BeatSpec(key="library", at=0.12, text_hint="not just another library", visual_action="Show a normal library path blocked."),
                BeatSpec(key="privilege", at=0.32, text_hint="runs with privileges", visual_action="Highlight the kernel zone."),
                BeatSpec(key="programs", at=0.50, text_hint="browser, shell, editor", visual_action="Place several apps in user mode."),
                BeatSpec(key="boundary", at=0.68, text_hint="guarded boundary", visual_action="Draw the boundary."),
                BeatSpec(key="isolation", at=0.86, text_hint="without letting one program", visual_action="Show isolation between programs."),
            ],
        ),
        SceneSpec(
            key="Scene3_SyscallGateEN",
            title="The controlled entry",
            duration_seconds=scene_duration,
            layout="syscall_gate",
            text=(
                "When a program needs protected work, it does not jump into kernel code directly. "
                "It prepares a request, places arguments where the calling convention expects them, "
                "and uses a CPU instruction that enters the kernel through a known gate. That gate "
                "is narrow on purpose: Linux can inspect what is being asked before it acts."
            ),
            visual_intent="Show a request token crossing a syscall gate instead of a direct jump.",
            beats=[
                BeatSpec(key="need_work", at=0.10, text_hint="needs protected work", visual_action="Show a user request token."),
                BeatSpec(key="no_jump", at=0.28, text_hint="does not jump", visual_action="Block a direct jump into the kernel."),
                BeatSpec(key="arguments", at=0.46, text_hint="places arguments", visual_action="Load argument slots beside the request."),
                BeatSpec(key="cpu_entry", at=0.66, text_hint="CPU instruction", visual_action="Move through the CPU entry gate."),
                BeatSpec(key="inspect", at=0.86, text_hint="inspect what is being asked", visual_action="Focus the kernel validation step."),
            ],
        ),
        SceneSpec(
            key="Scene4_MemoryEN",
            title="Virtual memory translation",
            duration_seconds=scene_duration,
            layout="memory_translation",
            text=(
                "Memory has the same pattern. A process sees virtual addresses, not raw RAM cells. "
                "The CPU and MMU consult page tables that the kernel manages, then translate a "
                "virtual page into a physical frame. That is why two programs can both use an "
                "address that looks identical, while Linux still keeps their real memory separate."
            ),
            visual_intent="Map virtual addresses through page tables into physical RAM frames.",
            beats=[
                BeatSpec(key="virtual", at=0.10, text_hint="virtual addresses", visual_action="Show a process virtual address space."),
                BeatSpec(key="mmu", at=0.30, text_hint="CPU and MMU", visual_action="Route an address through the MMU."),
                BeatSpec(key="tables", at=0.50, text_hint="page tables", visual_action="Reveal page table entries."),
                BeatSpec(key="frame", at=0.70, text_hint="physical frame", visual_action="Highlight the selected RAM frame."),
                BeatSpec(key="separate", at=0.88, text_hint="keeps their real memory separate", visual_action="Compare two isolated processes."),
            ],
        ),
        SceneSpec(
            key="Scene5_SchedulerEN",
            title="The scheduler shares time",
            duration_seconds=scene_duration,
            layout="scheduler_timeline",
            text=(
                "The same kernel also decides who runs next. A computer may feel like many programs "
                "are running at once, but each CPU core executes one thread at a time. The scheduler "
                "chooses a runnable task, gives it a slice of time, then switches when the slice ends, "
                "the task blocks, or a higher priority task needs attention."
            ),
            visual_intent="Show runnable tasks moving across a CPU time-slice timeline.",
            beats=[
                BeatSpec(key="many_programs", at=0.10, text_hint="many programs", visual_action="Show multiple runnable tasks."),
                BeatSpec(key="one_core", at=0.30, text_hint="one thread at a time", visual_action="Focus one CPU lane."),
                BeatSpec(key="choose", at=0.48, text_hint="chooses a runnable task", visual_action="Move a task onto the CPU."),
                BeatSpec(key="slice", at=0.68, text_hint="slice of time", visual_action="Animate a time slice on the timeline."),
                BeatSpec(key="switch", at=0.88, text_hint="then switches", visual_action="Switch to the next task."),
            ],
        ),
        SceneSpec(
            key="Scene6_RegistersEN",
            title="CPU state makes switching possible",
            duration_seconds=scene_duration,
            layout="cpu_registers",
            text=(
                "A context switch is not magic. The kernel saves the important CPU state for the "
                "thread that is leaving: instruction pointer, stack pointer, and registers. Then it "
                "loads the saved state for another thread. After that, the CPU continues as if the "
                "new thread had simply been paused and resumed."
            ),
            visual_intent="Show register values saved from one task and restored into another.",
            beats=[
                BeatSpec(key="switch", at=0.10, text_hint="context switch", visual_action="Show two tasks beside a CPU register panel."),
                BeatSpec(key="save", at=0.32, text_hint="saves CPU state", visual_action="Copy registers into task A state."),
                BeatSpec(key="ip_sp", at=0.50, text_hint="instruction pointer, stack pointer", visual_action="Highlight IP and SP rows."),
                BeatSpec(key="load", at=0.70, text_hint="loads the saved state", visual_action="Load task B state into CPU."),
                BeatSpec(key="resume", at=0.88, text_hint="paused and resumed", visual_action="Resume task B on the CPU."),
            ],
        ),
        SceneSpec(
            key="Scene7_HardwareEN",
            title="Hardware access is mediated",
            duration_seconds=scene_duration,
            layout="hardware_path",
            text=(
                "Disk and network access follow the same design. User programs ask for work, the "
                "kernel validates the request, drivers speak to hardware, and completion comes back "
                "as data or an error. This mediated path is slower than a fantasy direct wire, but "
                "it is what makes permissions, filesystems, devices, and isolation work together."
            ),
            visual_intent="Trace user request, kernel validation, driver, hardware, and return.",
            beats=[
                BeatSpec(key="ask", at=0.10, text_hint="programs ask", visual_action="Send a request from user space."),
                BeatSpec(key="validate", at=0.30, text_hint="kernel validates", visual_action="Focus a validation checkpoint."),
                BeatSpec(key="driver", at=0.50, text_hint="drivers speak", visual_action="Route through a driver block."),
                BeatSpec(key="hardware", at=0.70, text_hint="hardware", visual_action="Pulse disk and network devices."),
                BeatSpec(key="return", at=0.88, text_hint="data or an error", visual_action="Return a result token."),
            ],
        ),
        SceneSpec(
            key="Scene8_RecapEN",
            title="The takeaway",
            duration_seconds=scene_duration,
            layout="recap_map",
            text=(
                "So the useful mental model is this: programs ask, the kernel decides, and the "
                "hardware is touched through controlled paths. That is why Linux can feel simple "
                "at the terminal while still protecting the whole system underneath. Once you see "
                "that pattern, syscalls, virtual memory, scheduling, and drivers stop looking like "
                "separate mysteries and start looking like one operating system design."
            ),
            visual_intent="Summarize the ask-decide-perform model.",
            beats=[
                BeatSpec(key="ask", at=0.14, text_hint="programs ask", visual_action="Show user programs asking."),
                BeatSpec(key="decide", at=0.34, text_hint="kernel decides", visual_action="Move focus to the kernel."),
                BeatSpec(key="perform", at=0.56, text_hint="hardware is touched", visual_action="Move focus to hardware."),
                BeatSpec(key="patterns", at=0.74, text_hint="syscalls, virtual memory, scheduling", visual_action="Reveal the mechanism map."),
                BeatSpec(key="simple", at=0.88, text_hint="terminal while still protecting", visual_action="Show final summary."),
            ],
        ),
    ]
    if target < 180:
        short_duration = max(15, round(target / 3))
        scenes = scenes[:3]
        for scene in scenes:
            scene.duration_seconds = short_duration
    return VideoBlueprint(
        title=title,
        theme=safe_theme,
        slug="prompt-to-kernel-video",
        target_duration_seconds=target,
        audience="Developers learning Linux internals from visual explanations.",
        teaching_goal=f"Answer the user prompt with a concise Linux systems explanation: {prompt[:180]}",
        style_notes="Dark technical visual style, stable cards, clear arrows, one active concept at a time.",
        scenes=scenes,
    )


class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def generate_blueprint(
        self,
        prompt: str,
        theme: str | None,
        target_duration_seconds: int | None,
    ) -> VideoBlueprint:
        effective_target = target_duration_seconds or self.settings.default_target_duration_seconds
        if self.settings.fake_llm:
            logger.info("llm.fake_blueprint.start prompt_chars=%d theme=%s", len(prompt), theme)
            return fake_blueprint(prompt, theme, effective_target)

        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required unless VIDEO_API_FAKE_LLM=1")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("The openai package is required for LLM generation") from exc

        client = OpenAI(
            api_key=self.settings.openai_api_key,
            base_url=self.settings.openai_base_url,
            timeout=self.settings.llm_timeout_seconds,
        )
        logger.info(
            "llm.request.start model=%s base_url=%s prompt_chars=%d theme=%s",
            self.settings.openai_model,
            self.settings.openai_base_url,
            len(prompt),
            theme,
        )
        user_prompt = {
            "prompt": prompt,
            "theme": theme or "linux-fondamentaux",
            "target_duration_seconds": effective_target,
            "generation_guidelines": _load_generation_guidelines(self.settings),
            "duration_policy": {
                "default_target_seconds": self.settings.default_target_duration_seconds,
                "default_min_seconds": self.settings.default_min_duration_seconds,
                "for_180_to_300_second_targets": "Use 8 to 12 scenes, each around 20 to 40 seconds.",
                "narration": "Write enough spoken narration to fill the target duration; avoid short summaries.",
            },
            "approved_layouts": LAYOUTS,
            "required_schema": {
                "title": "string",
                "theme": "kebab-case string",
                "slug": "lowercase kebab-case string",
                "target_duration_seconds": effective_target,
                "audience": "string",
                "teaching_goal": "string",
                "style_notes": "string",
                "scenes": [
                    {
                        "key": "Scene1_HookEN",
                        "title": "string",
                        "duration_seconds": "integer planned duration for this scene",
                        "layout": "one approved layout string",
                        "text": "English narration for this scene",
                        "visual_intent": "concrete visual plan",
                        "beats": [
                            {
                                "key": "short_identifier",
                                "at": 0.1,
                                "text_hint": "spoken idea around this moment",
                                "visual_action": "exact visual action",
                            }
                        ],
                    }
                ],
            },
        }
        kwargs: dict[str, Any] = {}
        if self.settings.llm_response_format == "json_object":
            kwargs["response_format"] = {"type": "json_object"}
        response = client.chat.completions.create(
            model=self.settings.openai_model,
            temperature=self.settings.llm_temperature,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=True)},
            ],
            **kwargs,
        )
        content = response.choices[0].message.content or ""
        logger.info("llm.request.done model=%s response_chars=%d", self.settings.openai_model, len(content))
        data = _coerce_blueprint_shape(_extract_json_object(content))
        try:
            return VideoBlueprint.model_validate(data)
        except ValidationError as exc:
            logger.warning("llm.blueprint.invalid errors=%s", exc)
            repaired = self.repair_blueprint(prompt, data, str(exc))
            return repaired

    def repair_blueprint(self, prompt: str, previous: Any, error_report: str) -> VideoBlueprint:
        if self.settings.fake_llm:
            logger.info("llm.fake_repair.start prompt_chars=%d", len(prompt))
            target = previous.get("target_duration_seconds") if isinstance(previous, dict) else None
            return fake_blueprint(prompt, target_duration_seconds=target)
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for LLM repair")
        from openai import OpenAI

        client = OpenAI(
            api_key=self.settings.openai_api_key,
            base_url=self.settings.openai_base_url,
            timeout=self.settings.llm_timeout_seconds,
        )
        logger.info(
            "llm.repair.start model=%s base_url=%s error_chars=%d",
            self.settings.openai_model,
            self.settings.openai_base_url,
            len(error_report),
        )
        response = client.chat.completions.create(
            model=self.settings.openai_model,
            temperature=0.15,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task": "Repair this video blueprint JSON so it validates.",
                            "original_prompt": prompt,
                            "previous": previous,
                            "errors": error_report,
                            "generation_guidelines": _load_generation_guidelines(self.settings),
                            "approved_layouts": LAYOUTS,
                            "repair_rules": (
                                "Keep target_duration_seconds, use 8-12 scenes for 3-5 minute videos, "
                                "include duration_seconds and approved layout on every scene, and write "
                                "enough narration to satisfy the duration target."
                            ),
                        },
                        ensure_ascii=True,
                    ),
                },
            ],
        )
        content = response.choices[0].message.content or ""
        logger.info("llm.repair.done model=%s response_chars=%d", self.settings.openai_model, len(content))
        return VideoBlueprint.model_validate(_coerce_blueprint_shape(_extract_json_object(content)))
