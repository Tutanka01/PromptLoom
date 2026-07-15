import { z } from "zod";
import type { SegOption } from "../../components/form";
import type {
  CaptionMode,
  ProductionMode,
  VideoCreateRequest,
} from "../../api/types";
import type { EffectiveCaps } from "../../lib/capabilities";

export const THEME_SUGGESTIONS = ["math", "cs", "physics", "biology", "chemistry", "engineering"];

export const MODE_OPTIONS: SegOption<ProductionMode>[] = [
  { value: "technical", label: "Technique", hint: "Explication sobre, diagrammes d'abord." },
  { value: "editorial", label: "Éditorial", hint: "Narration documentée, visuels variés." },
  { value: "cinematic", label: "Cinématique", hint: "Montage animé, rendu Remotion." },
];

export const STRATEGY_OPTIONS: SegOption<"diagrams" | "hybrid" | "motion_first">[] = [
  { value: "diagrams", label: "Diagrammes", hint: "Schémas générés uniquement." },
  { value: "hybrid", label: "Hybride", hint: "Diagrammes + médias quand pertinent." },
  { value: "motion_first", label: "Motion", hint: "Priorité au mouvement et aux séquences." },
];

export const CAPTION_OPTIONS: SegOption<CaptionMode>[] = [
  { value: "off", label: "Aucun", hint: "Vidéo propre, sans piste de sous-titres." },
  { value: "full", label: "Incrustés", hint: "Sous-titres continus + fichier .srt/.vtt." },
];

// The zod bounds are the API's absolute contract; the UI narrows them further
// from /v1/capabilities (sliders, selects) so values can't drift out of range.
export const formSchema = z
  .object({
    prompt: z
      .string()
      .trim()
      .min(10, "Au moins 10 caractères.")
      .max(4000, "4000 caractères maximum."),
    theme: z.string().trim().max(80, "80 caractères maximum.").optional(),
    multilang: z.boolean(),
    language: z.string(),
    languages: z.array(z.string()).max(8, "8 langues maximum."),
    target_duration_seconds: z.number().int().min(20).max(900),
    quality_profile: z.enum(["draft", "standard", "high"]),
    production_mode: z.enum(["technical", "editorial", "cinematic"]),
    render_engine: z.enum(["auto", "manim", "remotion"]),
    research_enabled: z.boolean(),
    research_max_sources: z.number().int().min(3).max(20),
    visuals_strategy: z.enum(["diagrams", "hybrid", "motion_first"]),
    visuals_allow_stock: z.boolean(),
    visuals_max_assets: z.number().int().min(0).max(12),
    captions: z.enum(["off", "keywords", "full"]),
    // "auto" = laisser le serveur choisir (défaut moteur); sinon un id de
    // GET /v1/voices, validé côté serveur (422 si incompatible).
    voice: z.string(),
    callback_url: z
      .string()
      .trim()
      .url("URL invalide.")
      .optional()
      .or(z.literal("")),
  })
  .refine((v) => !(v.production_mode === "cinematic" && v.render_engine === "manim"), {
    message: "Le mode cinématique exige Remotion.",
    path: ["render_engine"],
  })
  .refine((v) => !v.multilang || v.languages.length >= 1, {
    message: "Sélectionnez au moins une langue.",
    path: ["languages"],
  });

export type FormValues = z.infer<typeof formSchema>;

/** Initial values derived from the deployment's effective state. */
export function makeDefaults(caps: EffectiveCaps): FormValues {
  const profile = caps.defaults.qualityProfile === "draft" ? "draft" : "standard";
  const allowed = caps.languagesByProfile[profile] ?? caps.languages.map((l) => l.code);
  const language = ["fr", "en"].find((code) => allowed.includes(code)) ?? allowed[0] ?? "en";
  const secondary = language === "fr" ? "en" : "fr";
  return {
    prompt: "",
    theme: "",
    multilang: false,
    language,
    languages: allowed.includes(secondary) ? [language, secondary] : [language],
    target_duration_seconds: caps.limits.duration.default,
    quality_profile: profile,
    production_mode: caps.defaults.productionMode,
    render_engine: "auto",
    research_enabled: false,
    research_max_sources: caps.limits.researchMaxSources.default,
    visuals_strategy: "diagrams",
    visuals_allow_stock: false,
    visuals_max_assets: caps.limits.visualsMaxAssets.default,
    captions: caps.defaults.captionMode === "full" ? "full" : "off",
    voice: "auto",
    callback_url: "",
  };
}

// Translate the flat form into the API request. Features the deployment does
// not provide are forced off (a request must never ask for what the server
// said it cannot do), and `required` follows `enabled`: an explicitly
// requested research that lost its provider must fail loudly, never silently.
export function toRequest(v: FormValues, caps: EffectiveCaps): VideoCreateRequest {
  const researchOn = caps.research.available && v.research_enabled;
  const allowStock = caps.stockAssets.available && v.visuals_allow_stock;
  const body: VideoCreateRequest = {
    prompt: v.prompt.trim(),
    target_duration_seconds: v.target_duration_seconds,
    quality_profile: v.quality_profile,
    production_mode: v.production_mode,
    captions: v.captions,
    research: {
      enabled: researchOn,
      required: researchOn,
      max_sources: v.research_max_sources,
    },
    visuals: {
      strategy: v.visuals_strategy,
      allow_stock: allowStock,
      max_assets: v.visuals_max_assets,
    },
  };
  if (v.theme?.trim()) body.theme = v.theme.trim();
  if (v.render_engine !== "auto") body.render_engine = v.render_engine;
  if (v.voice && v.voice !== "auto") body.voice = v.voice;
  if (v.callback_url?.trim()) body.callback_url = v.callback_url.trim();

  if (v.multilang) {
    body.languages = v.languages;
  } else {
    body.language = v.language;
  }
  return body;
}
