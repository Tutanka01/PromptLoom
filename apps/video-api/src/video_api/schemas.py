from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


CLASS_KEY_RE = re.compile(r"^Scene\d+_[A-Za-z0-9]+EN$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class VideoCreateRequest(BaseModel):
    prompt: str = Field(min_length=10, max_length=4000)
    theme: str | None = Field(default=None, max_length=80)
    language: Literal["en"] = "en"
    target_duration_seconds: int | None = Field(default=None, ge=45, le=900)
    quality_profile: Literal["final"] = "final"
    callback_url: str | None = None


class VideoCreateResponse(BaseModel):
    job_id: str
    status_url: str
    download_url: str | None = None


class VideoStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: int
    current_step: str | None = None
    error_message: str | None = None
    download_url: str | None = None
    report_url: str | None = None


class BeatSpec(BaseModel):
    key: str = Field(min_length=2, max_length=40)
    at: float = Field(ge=0.0, le=1.0)
    text_hint: str = Field(min_length=2, max_length=240)
    visual_action: str = Field(min_length=2, max_length=280)

    @field_validator("key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        value = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip()).strip("_").lower()
        return value or "beat"


SceneLayout = Literal[
    "process_pipeline",
    "privilege_boundary",
    "memory_translation",
    "scheduler_timeline",
    "syscall_gate",
    "cpu_registers",
    "hardware_path",
    "recap_map",
]


class SceneSpec(BaseModel):
    key: str
    title: str = Field(min_length=2, max_length=80)
    text: str = Field(min_length=30, max_length=1600)
    duration_seconds: int = Field(default=30, ge=15, le=75)
    layout: SceneLayout = "process_pipeline"
    visual_intent: str = Field(min_length=10, max_length=500)
    beats: list[BeatSpec] = Field(min_length=3, max_length=8)

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        value = value.strip()
        if not CLASS_KEY_RE.match(value):
            raise ValueError("scene key must look like Scene1_HookEN")
        return value

    @model_validator(mode="after")
    def validate_beats_order(self) -> "SceneSpec":
        ats = [beat.at for beat in self.beats]
        if ats != sorted(ats):
            raise ValueError("scene beats must be sorted by at")
        if ats[-1] < 0.75:
            raise ValueError("last useful beat should be near the end of the narration")
        return self


class VideoBlueprint(BaseModel):
    title: str = Field(min_length=3, max_length=100)
    theme: str = Field(min_length=2, max_length=80)
    slug: str
    target_duration_seconds: int = Field(default=240, ge=45, le=900)
    audience: str = Field(min_length=5, max_length=240)
    teaching_goal: str = Field(min_length=10, max_length=400)
    style_notes: str = Field(min_length=10, max_length=700)
    scenes: list[SceneSpec] = Field(min_length=3, max_length=14)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        value = value.strip().lower()
        if not SLUG_RE.match(value):
            raise ValueError("slug must use lowercase kebab-case")
        return value

    @model_validator(mode="after")
    def validate_scene_sequence(self) -> "VideoBlueprint":
        expected = [f"Scene{i}_" for i in range(1, len(self.scenes) + 1)]
        actual = [scene.key for scene in self.scenes]
        for prefix, key in zip(expected, actual, strict=True):
            if not key.startswith(prefix):
                raise ValueError("scene keys must be ordered Scene1_..., Scene2_...")
        if len(set(actual)) != len(actual):
            raise ValueError("scene keys must be unique")
        if self.target_duration_seconds >= 180 and len(self.scenes) < 8:
            raise ValueError("3-5 minute videos need at least 8 scenes")
        if self.target_duration_seconds <= 300 and len(self.scenes) > 12:
            raise ValueError("3-5 minute videos should use at most 12 scenes")

        planned_duration = sum(scene.duration_seconds for scene in self.scenes)
        lower = max(45, int(self.target_duration_seconds * 0.75))
        upper = int(self.target_duration_seconds * 1.25)
        if planned_duration < lower or planned_duration > upper:
            raise ValueError(
                f"planned scene duration {planned_duration}s is outside target window {lower}-{upper}s"
            )

        if self.target_duration_seconds >= 180:
            estimated_narration = sum(_estimated_spoken_seconds(scene.text) for scene in self.scenes)
            min_narration = max(45, int(self.target_duration_seconds * 0.55))
            if estimated_narration < min_narration:
                raise ValueError(
                    f"estimated narration duration {estimated_narration}s is too short for target "
                    f"{self.target_duration_seconds}s"
                )
        return self


def _estimated_spoken_seconds(text: str) -> int:
    words = re.findall(r"\b[\w'-]+\b", text)
    return max(1, round(len(words) / 155 * 60))
