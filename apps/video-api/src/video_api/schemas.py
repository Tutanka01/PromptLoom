from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from video_api import timing
from video_api.languages import normalize_language

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


# How many languages a single request may fan out into. The primary language
# generates the master blueprint; every extra language re-renders a translation
# of it, so each one is a full render — keep the cap sane.
MAX_BATCH_LANGUAGES = 8

# Bounds of the create request, shared with GET /v1/capabilities so the
# advertised limits can never drift from the enforced ones.
PROMPT_MIN_CHARS = 10
PROMPT_MAX_CHARS = 4000
THEME_MAX_CHARS = 80
DURATION_MIN_SECONDS = 20
DURATION_MAX_SECONDS = 900
RESEARCH_SOURCES_MIN = 3
RESEARCH_SOURCES_MAX = 20
RESEARCH_SOURCES_DEFAULT = 10
VISUAL_ASSETS_MIN = 0
VISUAL_ASSETS_MAX = 12
VISUAL_ASSETS_DEFAULT = 4


ProductionMode = Literal["technical", "editorial", "cinematic"]
# Subtitle delivery, opt-in per request (Remotion engine):
#   "off"      -> clean video: no burned-in track AND no .srt/.vtt sidecar;
#   "full"     -> continuous burned-in subtitle track + .srt/.vtt sidecar;
#   "keywords" -> retained for compatibility, behaves like "full" (continuous).
# Default (when unset): "off" in every production mode.
CaptionMode = Literal["off", "keywords", "full"]
AssetStrategy = Literal["diagrams", "hybrid", "motion_first"]


class ResearchOptions(BaseModel):
    """Per-job grounding policy.

    ``enabled=None`` means "derive from production_mode": disabled for the
    backwards-compatible technical mode, enabled for editorial/cinematic.
    When enabled, ``required`` prevents a job from quietly pretending it was
    researched when no server-side research provider is configured.
    """

    enabled: bool | None = None
    required: bool = True
    max_sources: int = Field(
        default=RESEARCH_SOURCES_DEFAULT, ge=RESEARCH_SOURCES_MIN, le=RESEARCH_SOURCES_MAX
    )


class VisualOptions(BaseModel):
    strategy: AssetStrategy = "diagrams"
    allow_stock: bool | None = None
    max_assets: int = Field(default=VISUAL_ASSETS_DEFAULT, ge=VISUAL_ASSETS_MIN, le=VISUAL_ASSETS_MAX)


class ProductionOptions(BaseModel):
    """Versioned, persisted configuration resolved from a create request."""

    version: Literal[1] = 1
    mode: ProductionMode = "technical"
    render_engine: Literal["manim", "remotion"] | None = None
    research: ResearchOptions = Field(default_factory=ResearchOptions)
    visuals: VisualOptions = Field(default_factory=VisualOptions)
    captions: CaptionMode | None = None
    # Requested narration voice id (see GET /v1/voices). None = engine default
    # (which for MOSS means the free-running, non-pinned timbre).
    voice: str | None = Field(default=None, max_length=80)
    delivery_promise: Literal[
        "technical_explainer", "editorial_explainer", "motion_led_explainer"
    ] | None = None

    @model_validator(mode="after")
    def resolve_defaults(self) -> "ProductionOptions":
        advanced = self.mode in {"editorial", "cinematic"}
        if self.render_engine is None and advanced:
            self.render_engine = "remotion"
        if self.mode == "cinematic" and self.render_engine == "manim":
            raise ValueError("cinematic production mode requires render_engine='remotion'")
        if self.research.enabled is None:
            self.research.enabled = advanced
        if self.captions is None:
            self.captions = "off"
        if self.delivery_promise is None:
            self.delivery_promise = {
                "technical": "technical_explainer",
                "editorial": "editorial_explainer",
                "cinematic": "motion_led_explainer",
            }[self.mode]
        if advanced and self.visuals.strategy == "diagrams":
            self.visuals.strategy = "hybrid"
        if self.visuals.allow_stock is None:
            self.visuals.allow_stock = advanced
        return self


class VideoCreateRequest(BaseModel):
    prompt: str = Field(min_length=PROMPT_MIN_CHARS, max_length=PROMPT_MAX_CHARS)
    theme: str | None = Field(default=None, max_length=THEME_MAX_CHARS)
    language: str = Field(default="en", min_length=2, max_length=12)
    # Optional multi-language batch. When set with more than one language, the
    # request produces one video per language: identical content and structure,
    # only the spoken narration and on-screen text translated. The first entry is
    # the primary language (it generates the master blueprint); the rest translate
    # it. When omitted, `language` drives a single video as before.
    languages: list[str] | None = Field(default=None, max_length=MAX_BATCH_LANGUAGES)
    target_duration_seconds: int | None = Field(
        default=None, ge=DURATION_MIN_SECONDS, le=DURATION_MAX_SECONDS
    )
    # draft    = fast iteration: Kokoro voice, half-res render, no visual review.
    # standard = production defaults (Chatterbox, full-res final render).
    # high     = standard + visual review forced on (needs VIDEO_API_VISION_MODEL).
    # "final" is the legacy name, kept as an alias of standard.
    quality_profile: Literal["draft", "standard", "high", "final"] = "standard"
    # Per-job render/production controls. Existing callers omit these and keep
    # the historical technical pipeline selected by server configuration.
    render_engine: Literal["manim", "remotion"] | None = None
    production_mode: ProductionMode = "technical"
    research: ResearchOptions = Field(default_factory=ResearchOptions)
    visuals: VisualOptions = Field(default_factory=VisualOptions)
    # Subtitles, opt-in. Omit (or set "off") for a clean video with no subtitles
    # at all, or set "full" to force them on. See CaptionMode.
    captions: CaptionMode | None = None
    # Narration voice id, one of GET /v1/voices for the engine that will run
    # under the requested quality_profile. Omit for the engine default. In a
    # multi-language batch the same voice narrates every video, so it must
    # cover every requested language (422 otherwise).
    voice: str | None = Field(default=None, max_length=80)
    callback_url: str | None = None

    @field_validator("voice")
    @classmethod
    def normalize_voice(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        return normalize_language(value)

    @field_validator("languages")
    @classmethod
    def validate_languages(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized: list[str] = []
        for item in value:
            code = normalize_language(item)
            if code not in normalized:  # dedupe, preserve order
                normalized.append(code)
        if not normalized:
            return None
        return normalized

    @model_validator(mode="after")
    def validate_production_controls(self) -> "VideoCreateRequest":
        # Validate cross-field constraints at the HTTP schema boundary. Keeping
        # this in production_options() alone would turn an invalid combination
        # such as cinematic+Manim into an endpoint 500 instead of a clean 422.
        self.production_options()
        return self

    def resolved_languages(self) -> list[str]:
        """Ordered, de-duplicated languages to produce. The primary language is
        always first. Falls back to a single-element list built from `language`."""
        langs = list(self.languages or [])
        if not langs:
            return [self.language]
        # Ensure the explicit `language` (the primary) leads the list when the
        # caller set both fields without putting it first.
        if self.languages is None and self.language not in langs:
            langs.insert(0, self.language)
        return langs

    def production_options(self) -> ProductionOptions:
        return ProductionOptions(
            mode=self.production_mode,
            render_engine=self.render_engine,
            research=self.research,
            visuals=self.visuals,
            captions=self.captions,
            voice=self.voice,
        )


class BatchJobRef(BaseModel):
    job_id: str
    language: str
    is_primary: bool
    status_url: str


class VideoCreateResponse(BaseModel):
    job_id: str
    status_url: str
    download_url: str | None = None
    # Populated only for multi-language batches.
    batch_id: str | None = None
    jobs: list[BatchJobRef] | None = None


class VideoStatusResponse(BaseModel):
    job_id: str
    status: str
    language: str | None = None
    batch_id: str | None = None
    quality_profile: str | None = None
    render_engine: str | None = None
    production_mode: str | None = None
    progress: int
    current_step: str | None = None
    error_message: str | None = None
    download_url: str | None = None
    report_url: str | None = None
    # Repair loop visibility (see VideoJob model). `attempt_number` starts at 0
    # for the first run and increments on each pipeline retry; the ceiling is
    # `max_attempts`. `last_repair_reason` carries the exception message that
    # triggered the current retry (None on the first attempt).
    attempt_number: int | None = None
    max_attempts: int | None = None
    last_repair_reason: str | None = None


class BatchStatusResponse(BaseModel):
    batch_id: str
    languages: list[str]
    jobs: list[VideoStatusResponse]


class VoiceInfo(BaseModel):
    id: str
    label: str
    engine: str  # canonical family: kokoro | openai | moss
    # None = the voice covers every language the API accepts (voice cloning /
    # true multilingual voices).
    languages: list[str] | None = None
    description: str = ""
    is_default: bool = False


class VoicesResponse(BaseModel):
    # Engine family that synthesizes under the standard profile.
    engine: str
    # Effective family per quality profile (the draft profile forces kokoro).
    engine_by_profile: dict[str, str]
    voices: list[VoiceInfo]


# ---------------------------------------------------------------------------
# GET /v1/capabilities — effective deployment state (see capabilities.py).
# ---------------------------------------------------------------------------


class LanguageInfo(BaseModel):
    code: str
    name: str


class CapabilityFeature(BaseModel):
    """A server-side feature callers can request but never configure: it is
    available (a provider/model is configured in the environment) or not."""

    available: bool
    provider: str | None = None


class CapabilityFeatures(BaseModel):
    research: CapabilityFeature
    stock_assets: CapabilityFeature
    visual_review: CapabilityFeature


class CapabilityRange(BaseModel):
    min: int
    max: int
    default: int


class CapabilityLimits(BaseModel):
    prompt_max_chars: int
    theme_max_chars: int
    max_batch_languages: int
    target_duration_seconds: CapabilityRange
    research_max_sources: CapabilityRange
    visuals_max_assets: CapabilityRange


class CapabilityDefaults(BaseModel):
    production_mode: str
    caption_mode: str
    quality_profile: str
    render_engine: str


class CapabilitiesResponse(BaseModel):
    # TTS engine family under the standard profile, and per profile (draft
    # forces kokoro) — mirrors GET /v1/voices.
    engine: str
    engine_by_profile: dict[str, str]
    # Every language the API accepts, then the subset each profile's effective
    # TTS engine can actually speak.
    languages: list[LanguageInfo]
    languages_by_profile: dict[str, list[str]]
    # Whether GET /v1/voices returns at least one selectable voice per profile
    # (chatterbox exposes none; an empty MOSS voice bank exposes none).
    voice_selection_by_profile: dict[str, bool]
    render_engines: list[str]
    features: CapabilityFeatures
    limits: CapabilityLimits
    defaults: CapabilityDefaults


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
    duration_seconds: int = Field(default=30, ge=8, le=75)
    layout: SceneLayout = "concept_map"
    visual_intent: str = Field(min_length=10, max_length=500)
    beats: list[BeatSpec] = Field(min_length=3, max_length=8)
    source_ids: list[str] = Field(default_factory=list, max_length=12)

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
    target_duration_seconds: int = Field(default=240, ge=20, le=900)
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
        lower = max(10, int(self.target_duration_seconds * 0.75))
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


# ---------------------------------------------------------------------------
# Remotion engine blueprint
#
# Dedicated, decoupled contract for the Remotion render engine
# (VIDEO_API_RENDER_ENGINE=remotion). Unlike SceneSpec (Manim), a scene names a
# tested React component from a fixed palette and carries plain props, OR uses
# "Custom" to request free-form TSX written by the Remotion scene-coder. The
# field names mirror the Manim path where the shared downstream needs them
# (key, title, text/narration, duration_seconds) so segments / durations / TTS
# reuse the same plumbing. The duration + narration gates are shared with
# VideoBlueprint via video_api.timing, so a blueprint that validates here is
# guaranteed enough narration to clear verify_mp4.
# ---------------------------------------------------------------------------

REMOTION_PALETTE = (
    "TitleScene",
    "BulletScene",
    "FormulaScene",
    "CodeScene",
    "PlotScene",
    "DiagramScene",
    "ComparisonScene",
    "LayeredSystemScene",
    "TimelineScene",
    "TerminalScene",
    "MemoryScene",
    "FlowScene",
    "BarChartScene",
    "CounterScene",
    "QuoteScene",
    "SplitFocusScene",
    "ZoomNarrativeScene",
    "NetworkMapScene",
    "ImageScene",
    "FootageScene",
)

RemotionComponent = Literal[
    "TitleScene",
    "BulletScene",
    "FormulaScene",
    "CodeScene",
    "PlotScene",
    "DiagramScene",
    "ComparisonScene",
    "LayeredSystemScene",
    "TimelineScene",
    "TerminalScene",
    "MemoryScene",
    "FlowScene",
    "BarChartScene",
    "CounterScene",
    "QuoteScene",
    "SplitFocusScene",
    "ZoomNarrativeScene",
    "NetworkMapScene",
    "ImageScene",
    "FootageScene",
    "Custom",
]


RemotionTransition = Literal["auto", "fade", "rise", "slide-left", "scale", "slide-right", "wipe"]


# Art-direction palettes the LLM may pick from to suit a video's subject/tone.
# Mirror of THEMES in remotion/src/style/tokens.ts (parity enforced by
# tests/test_remotion_themes_parity.py). "default" reproduces the original
# dark-academic look exactly, so an un-themed render never regresses.
REMOTION_THEMES = (
    "default",
    "blueprint",
    "forest",
    "synthwave",
    "carbon",
    "plum",
)

RemotionArtDirection = Literal[
    "default",
    "blueprint",
    "forest",
    "synthwave",
    "carbon",
    "plum",
]


class RemotionBeat(BaseModel):
    """A narration anchor marking when the i-th visual item should appear.

    ``anchor`` is a short phrase copied verbatim from the scene's narration.
    After TTS, pipeline/align.py + pipeline/beats.py locate it in the word-level
    alignment and turn it into a cue ratio consumed by the React components
    (``props.cues``), so each item reveals exactly when its words are spoken.
    """

    anchor: str = Field(min_length=3, max_length=80)
    note: str = Field(default="", max_length=120)


class RemotionScene(BaseModel):
    key: str
    title: str = Field(min_length=2, max_length=80)
    # Spoken narration for this scene. Exposed downstream as `.text` so the
    # shared segments/TTS code can treat Manim and Remotion scenes uniformly.
    narration: str = Field(min_length=30, max_length=1600)
    duration_seconds: int = Field(default=30, ge=8, le=90)
    component: RemotionComponent = "BulletScene"
    props: dict[str, Any] = Field(default_factory=dict)
    # Narration anchors, one per visual item in display order. Optional: empty
    # means the component keeps its default evenly-spaced timings.
    beats: list[RemotionBeat] = Field(default_factory=list, max_length=10)
    # Scene-to-scene hand-off style; "auto" cycles deterministically by index.
    transition: RemotionTransition = "auto"
    # Concrete visual plan; only consumed when component == "Custom" (drives the
    # Remotion scene-coder). Harmless for palette scenes.
    visual_intent: str = Field(default="", max_length=600)
    # Stable IDs from research.json. They are provenance metadata, not visible
    # URLs, and survive translation/repair unchanged.
    source_ids: list[str] = Field(default_factory=list, max_length=12)

    @property
    def text(self) -> str:
        return self.narration

    @property
    def is_custom(self) -> bool:
        return self.component == "Custom"

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        value = value.strip()
        if not CLASS_KEY_RE.match(value):
            raise ValueError("scene key must look like Scene1_HookEN")
        return value


class RemotionBlueprint(BaseModel):
    title: str = Field(min_length=3, max_length=100)
    theme: str = Field(min_length=2, max_length=80)
    slug: str
    target_duration_seconds: int = Field(default=240, ge=20, le=900)
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
    # Art-direction palette (see THEMES in remotion/src/style/tokens.ts). The LLM
    # picks one to suit the subject/tone; "default" keeps the original look.
    # Unknown/invalid values are clamped to "default" in remotion_blueprint.py.
    art_direction: RemotionArtDirection = "default"
    scenes: list[RemotionScene] = Field(min_length=3, max_length=14)
    # Quality degradations recorded during generation (placeholder props that
    # survived targeted retries, dropped anchors, ...). Empty on a clean
    # blueprint; surfaced under `quality` in report.json so a "completed" job
    # can be told apart from a quietly degraded one.
    degradations: list[str] = Field(default_factory=list)

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
    def validate_scene_sequence(self) -> "RemotionBlueprint":
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
        lower = max(10, int(self.target_duration_seconds * 0.75))
        upper = int(self.target_duration_seconds * 1.25)
        if planned_duration < lower or planned_duration > upper:
            raise ValueError(
                f"planned scene duration {planned_duration}s is outside target window {lower}-{upper}s"
            )

        estimated_narration = sum(_estimated_spoken_seconds(scene.narration) for scene in self.scenes)
        min_narration = timing.required_narration_seconds(self.target_duration_seconds)
        if estimated_narration < min_narration:
            needed_words = timing.required_total_words(self.target_duration_seconds)
            have_words = sum(timing.word_count(scene.narration) for scene in self.scenes)
            raise ValueError(
                f"estimated narration {estimated_narration}s is too short for target "
                f"{self.target_duration_seconds}s (need >= {min_narration}s of narration, "
                f"about {needed_words} words across all scenes; blueprint has {have_words})"
            )
        return self
