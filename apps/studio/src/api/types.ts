// Mirror of the public Pydantic contracts in
// apps/video-api/src/video_api/schemas.py. Kept intentionally small: only the
// fields the UI reads or sends.

export type ProductionMode = "technical" | "editorial" | "cinematic";
export type QualityProfile = "draft" | "standard" | "high";
export type RenderEngine = "manim" | "remotion";
export type CaptionMode = "off" | "keywords" | "full";
export type AssetStrategy = "diagrams" | "hybrid" | "motion_first";

// The `status` field walks the pipeline (see production.py `_update`). It is
// both the lifecycle state and the coarse stage, so the UI keys the Stage Rail
// and the status pill off it.
export type JobStatus =
  | "queued"
  | "waiting_for_master"
  | "planning"
  | "generating_sources"
  | "voice_generation"
  | "render_final"
  | "assemble_final"
  | "visual_review"
  | "verify_final"
  // Legacy statuses from historical jobs still in the DB (the low-quality proxy
  // render was removed; the visual review now inspects the final render).
  | "render_low_quality"
  | "assemble_low_quality"
  | "verify_low_quality"
  | "completed"
  | "cancelled"
  | "failed_generation"
  | "failed_render"
  | "failed_quality"
  | "failed_visual_review"
  | "failed_stale"
  // Be tolerant of any future server-side status.
  | (string & {});

export interface ResearchOptions {
  enabled?: boolean | null;
  required?: boolean;
  max_sources?: number;
}

export interface VisualOptions {
  strategy?: AssetStrategy;
  allow_stock?: boolean | null;
  max_assets?: number;
}

export interface VideoCreateRequest {
  prompt: string;
  theme?: string | null;
  language?: string;
  languages?: string[] | null;
  target_duration_seconds?: number | null;
  quality_profile?: QualityProfile;
  render_engine?: RenderEngine | null;
  production_mode?: ProductionMode;
  research?: ResearchOptions;
  visuals?: VisualOptions;
  captions?: CaptionMode | null;
  // Narration voice id from GET /v1/voices. Omit for the engine default.
  voice?: string | null;
  callback_url?: string | null;
}

// Engine families exposed by GET /v1/voices (moss covers moss + moss-remote).
export type VoiceEngine = "kokoro" | "openai" | "moss" | "chatterbox" | (string & {});

export interface VoiceInfo {
  id: string;
  label: string;
  engine: VoiceEngine;
  // null = the voice covers every language the API accepts (voice cloning).
  languages: string[] | null;
  description: string;
  is_default: boolean;
}

export interface VoicesResponse {
  // Engine family under the standard profile.
  engine: VoiceEngine;
  // Effective family per quality profile (draft forces kokoro).
  engine_by_profile: Record<string, VoiceEngine>;
  voices: VoiceInfo[];
}

export interface BatchJobRef {
  job_id: string;
  language: string;
  is_primary: boolean;
  status_url: string;
}

export interface VideoCreateResponse {
  job_id: string;
  status_url: string;
  download_url?: string | null;
  batch_id?: string | null;
  jobs?: BatchJobRef[] | null;
}

export interface VideoStatus {
  job_id: string;
  status: JobStatus;
  language?: string | null;
  batch_id?: string | null;
  quality_profile?: string | null;
  render_engine?: string | null;
  production_mode?: string | null;
  progress: number;
  current_step?: string | null;
  error_message?: string | null;
  download_url?: string | null;
  report_url?: string | null;
}

export interface VideoListResponse {
  jobs: VideoStatus[];
  limit: number;
  offset: number;
}

export interface BatchStatusResponse {
  batch_id: string;
  languages: string[];
  jobs: VideoStatus[];
}

export interface HealthResponse {
  status: "ok" | "degraded";
  checks: Record<string, string>;
}

// report.json is free-form; we render what we recognise and pretty-print the
// rest, so keep it loose.
export type VideoReport = Record<string, unknown>;
