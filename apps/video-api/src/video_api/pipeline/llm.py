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
Return only valid JSON. The JSON must describe a complete video blueprint.
Every scene must have a key like Scene1_HookEN, Scene2_CoreIdeaEN.
Each scene needs narration text and 3 to 8 beats that map spoken ideas to visual actions.
The voice and image must explain the same idea at the same time."""


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


def fake_blueprint(prompt: str, theme: str | None = None) -> VideoBlueprint:
    safe_theme = theme or "linux-fondamentaux"
    title = "Prompt To Kernel Video"
    scenes = [
        SceneSpec(
            key="Scene1_HookEN",
            title="The visible command",
            text=(
                "A Linux command looks simple from the outside. You type one line, press enter, "
                "and a result appears. But the interesting part is the controlled path between "
                "the program, the kernel, and the hardware."
            ),
            visual_intent="Show a terminal command, then reveal the kernel path behind it.",
            beats=[
                BeatSpec(key="command", at=0.10, text_hint="A Linux command looks simple", visual_action="Show a terminal command."),
                BeatSpec(key="program", at=0.35, text_hint="from the outside", visual_action="Reveal the user program."),
                BeatSpec(key="kernel", at=0.62, text_hint="controlled path", visual_action="Connect the program to the kernel."),
                BeatSpec(key="hardware", at=0.86, text_hint="and the hardware", visual_action="Complete the path to hardware."),
            ],
        ),
        SceneSpec(
            key="Scene2_MechanismEN",
            title="The kernel boundary",
            text=(
                "The kernel is not just another library. It runs with privileges user programs do "
                "not have. That boundary is what lets Linux share the machine without letting one "
                "program overwrite everything else."
            ),
            visual_intent="Contrast user space with kernel space and show the privilege boundary.",
            beats=[
                BeatSpec(key="library", at=0.12, text_hint="not just another library", visual_action="Show a normal library path blocked."),
                BeatSpec(key="privilege", at=0.38, text_hint="runs with privileges", visual_action="Highlight the kernel zone."),
                BeatSpec(key="boundary", at=0.64, text_hint="That boundary", visual_action="Draw the boundary."),
                BeatSpec(key="isolation", at=0.86, text_hint="without letting one program", visual_action="Show isolation between programs."),
            ],
        ),
        SceneSpec(
            key="Scene3_RecapEN",
            title="The takeaway",
            text=(
                "So the useful mental model is this: programs ask, the kernel decides, and the "
                "hardware is touched through controlled paths. That is why Linux can feel simple "
                "at the terminal while still protecting the whole system underneath."
            ),
            visual_intent="Summarize the ask-decide-perform model.",
            beats=[
                BeatSpec(key="ask", at=0.14, text_hint="programs ask", visual_action="Show user programs asking."),
                BeatSpec(key="decide", at=0.42, text_hint="kernel decides", visual_action="Move focus to the kernel."),
                BeatSpec(key="perform", at=0.68, text_hint="hardware is touched", visual_action="Move focus to hardware."),
                BeatSpec(key="simple", at=0.88, text_hint="terminal while still protecting", visual_action="Show final summary."),
            ],
        ),
    ]
    return VideoBlueprint(
        title=title,
        theme=safe_theme,
        slug="prompt-to-kernel-video",
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
        if self.settings.fake_llm:
            logger.info("llm.fake_blueprint.start prompt_chars=%d theme=%s", len(prompt), theme)
            return fake_blueprint(prompt, theme)

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
            "target_duration_seconds": target_duration_seconds,
            "required_schema": {
                "title": "string",
                "theme": "kebab-case string",
                "slug": "lowercase kebab-case string",
                "audience": "string",
                "teaching_goal": "string",
                "style_notes": "string",
                "scenes": [
                    {
                        "key": "Scene1_HookEN",
                        "title": "string",
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
        data = _extract_json_object(content)
        try:
            return VideoBlueprint.model_validate(data)
        except ValidationError as exc:
            logger.warning("llm.blueprint.invalid errors=%s", exc)
            repaired = self.repair_blueprint(prompt, data, str(exc))
            return repaired

    def repair_blueprint(self, prompt: str, previous: Any, error_report: str) -> VideoBlueprint:
        if self.settings.fake_llm:
            logger.info("llm.fake_repair.start prompt_chars=%d", len(prompt))
            return fake_blueprint(prompt)
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
                        },
                        ensure_ascii=True,
                    ),
                },
            ],
        )
        content = response.choices[0].message.content or ""
        logger.info("llm.repair.done model=%s response_chars=%d", self.settings.openai_model, len(content))
        return VideoBlueprint.model_validate(_extract_json_object(content))
