from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from video_api import timing

# ---------------------------------------------------------------------------
# Visual review
# ---------------------------------------------------------------------------

_DIMENSION_WEIGHTS: dict[str, float] = {
    "narration_match": 0.35,
    "readability": 0.20,
    "framing": 0.20,
    "density": 0.15,
    "not_blank": 0.10,
}


class VisualIssue(BaseModel):
    scene_key: str
    dimension: str
    severity: Literal["blocker", "major", "minor"]
    message: str
    suggestion: str = ""


class SceneVisualScore(BaseModel):
    scene_key: str
    timestamp: float
    dimensions: dict[str, float]
    score: float


class VisualReviewResult(BaseModel):
    score: float
    passed: bool
    scene_scores: list[SceneVisualScore]
    issues: list[VisualIssue]
    summary: str

    def repair_hint(self) -> str:
        """One-paragraph summary of blocker+major issues for the LLM repair prompt."""
        critical = [i for i in self.issues if i.severity in ("blocker", "major")]
        if not critical:
            return f"Visual review failed with score {self.score:.1f}/100 but no major issues were identified."
        by_scene: dict[str, list[VisualIssue]] = {}
        for issue in critical:
            by_scene.setdefault(issue.scene_key, []).append(issue)
        lines = [f"Visual review failed (score={self.score:.1f}/100). Issues requiring fixes:"]
        for scene_key, issues in by_scene.items():
            for issue in issues:
                suggestion = f" Suggestion: {issue.suggestion}" if issue.suggestion else ""
                lines.append(f"  [{issue.severity.upper()}] {scene_key} / {issue.dimension}: {issue.message}.{suggestion}")
        return "\n".join(lines)


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
    # Short on-screen text actually rendered on a card. Distinct from visual_action,
    # which is an instruction to the renderer ("Reveal the central question card").
    # When the LLM omits it, we derive it from the spoken idea (text_hint).
    label: str = Field(default="", max_length=42)

    @field_validator("key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        value = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip()).strip("_").lower()
        return value or "beat"

    @model_validator(mode="after")
    def fill_label(self) -> "BeatSpec":
        if not self.label.strip():
            self.label = _short_label(self.text_hint)
        else:
            self.label = _short_label(self.label)
        return self


SubjectArea = Literal[
    "math",
    "physics",
    "cs",
    "biology",
    "chemistry",
    "engineering",
    "general_stem",
]

Difficulty = Literal["intro", "intermediate", "advanced"]

SceneLayout = Literal[
    "concept_map",
    "process_flow",
    "layered_system",
    "timeline",
    "equation_transform",
    "graph_plot",
    "comparison_table",
    "cycle_diagram",
    "spatial_model",
    "recap_map",
]


class SceneSpec(BaseModel):
    key: str
    title: str = Field(min_length=2, max_length=80)
    text: str = Field(min_length=30, max_length=1600)
    duration_seconds: int = Field(default=30, ge=15, le=75)
    layout: SceneLayout = "concept_map"
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
    subject_area: SubjectArea = "general_stem"
    difficulty: Difficulty = "intro"
    audience: str = Field(min_length=5, max_length=240)
    teaching_goal: str = Field(min_length=10, max_length=400)
    learning_objectives: list[str] = Field(
        default_factory=lambda: ["Explain the core idea clearly."],
        min_length=1,
        max_length=5,
    )
    style_notes: str = Field(min_length=10, max_length=700)
    scenes: list[SceneSpec] = Field(min_length=3, max_length=14)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        value = value.strip().lower()
        if not SLUG_RE.match(value):
            raise ValueError("slug must use lowercase kebab-case")
        return value

    @field_validator("learning_objectives")
    @classmethod
    def validate_learning_objectives(cls, value: list[str]) -> list[str]:
        cleaned = [" ".join(item.split()) for item in value if item and item.strip()]
        if not cleaned:
            raise ValueError("learning_objectives must contain at least one objective")
        if any(len(item) > 180 for item in cleaned):
            raise ValueError("learning_objectives entries must stay concise")
        return cleaned

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

        # Pre-flight narration gate. Aligned with the final render gate
        # (timing.minimum_final_duration) so a blueprint that validates here is
        # guaranteed enough spoken content to clear verify_mp4 after rendering.
        estimated_narration = sum(_estimated_spoken_seconds(scene.text) for scene in self.scenes)
        min_narration = timing.required_narration_seconds(self.target_duration_seconds)
        if estimated_narration < min_narration:
            needed_words = timing.required_total_words(self.target_duration_seconds)
            have_words = sum(timing.word_count(scene.text) for scene in self.scenes)
            raise ValueError(
                f"estimated narration {estimated_narration}s is too short for target "
                f"{self.target_duration_seconds}s (need >= {min_narration}s of narration, "
                f"about {needed_words} words across all scenes; blueprint has {have_words})"
            )
        return self


def _short_label(text: str, limit: int = 40) -> str:
    """Turn a spoken-idea hint into a compact, on-screen card label.

    Drops trailing punctuation and clips at a word boundary so cards never show
    a phrase cut mid-word.
    """
    compact = " ".join(text.replace("\n", " ").split()).strip(" .,:;—-")
    if len(compact) <= limit:
        return compact
    clipped = compact[:limit].rsplit(" ", 1)[0].rstrip(" .,:;—-")
    return (clipped or compact[:limit]).rstrip() + "…"


def _estimated_spoken_seconds(text: str) -> int:
    return timing.estimated_spoken_seconds(text)
