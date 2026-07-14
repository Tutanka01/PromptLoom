import { z } from "zod";
import type { SegOption } from "../../components/form";
import type {
  CaptionMode,
  ProductionMode,
  QualityProfile,
  VideoCreateRequest,
} from "../../api/types";

// MOSS-TTS v1.5 supported output languages (see api-reference.md). Primary
// European set first for quick reach.
export const LANGUAGES: { code: string; name: string }[] = [
  { code: "en", name: "Anglais" },
  { code: "fr", name: "Français" },
  { code: "es", name: "Espagnol" },
  { code: "it", name: "Italien" },
  { code: "pt", name: "Portugais" },
  { code: "de", name: "Allemand" },
  { code: "nl", name: "Néerlandais" },
  { code: "ro", name: "Roumain" },
  { code: "pl", name: "Polonais" },
  { code: "cs", name: "Tchèque" },
  { code: "da", name: "Danois" },
  { code: "sv", name: "Suédois" },
  { code: "fi", name: "Finnois" },
  { code: "el", name: "Grec" },
  { code: "hu", name: "Hongrois" },
  { code: "mk", name: "Macédonien" },
  { code: "ru", name: "Russe" },
  { code: "tr", name: "Turc" },
  { code: "zh", name: "Chinois" },
  { code: "yue", name: "Cantonais" },
  { code: "ar", name: "Arabe" },
  { code: "he", name: "Hébreu" },
  { code: "hi", name: "Hindi" },
  { code: "ja", name: "Japonais" },
  { code: "ko", name: "Coréen" },
  { code: "ms", name: "Malais" },
  { code: "fa", name: "Persan" },
  { code: "sw", name: "Swahili" },
  { code: "tl", name: "Tagalog" },
  { code: "th", name: "Thaï" },
  { code: "vi", name: "Vietnamien" },
];

export const THEME_SUGGESTIONS = ["math", "cs", "physics", "biology", "chemistry", "engineering"];

export const QUALITY_OPTIONS: SegOption<QualityProfile>[] = [
  { value: "draft", label: "Brouillon", hint: "Itération rapide, demi-résolution, voix Kokoro." },
  { value: "standard", label: "Standard", hint: "Profil de production complet." },
  { value: "high", label: "Élevé", hint: "Standard + revue visuelle forcée." },
];

export const MODE_OPTIONS: SegOption<ProductionMode>[] = [
  { value: "technical", label: "Technique", hint: "Pipeline historique." },
  { value: "editorial", label: "Éditorial", hint: "Recherche + anti-diaporama, Remotion." },
  { value: "cinematic", label: "Cinématique", hint: "Remotion 60 fps, recherche par défaut." },
];

export const ENGINE_OPTIONS: SegOption<"auto" | "manim" | "remotion">[] = [
  { value: "auto", label: "Auto", hint: "Laisser le mode décider." },
  { value: "manim", label: "Manim", hint: "Rendu Python/Manim." },
  { value: "remotion", label: "Remotion", hint: "Rendu React/Remotion." },
];

export const STRATEGY_OPTIONS: SegOption<"diagrams" | "hybrid" | "motion_first">[] = [
  { value: "diagrams", label: "Diagrammes" },
  { value: "hybrid", label: "Hybride" },
  { value: "motion_first", label: "Motion" },
];

export const CAPTION_OPTIONS: SegOption<CaptionMode>[] = [
  { value: "off", label: "Aucun" },
  { value: "keywords", label: "Mots-clés" },
  { value: "full", label: "Complet" },
];

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
    research_required: z.boolean(),
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

export const defaultValues: FormValues = {
  prompt: "",
  theme: "",
  multilang: false,
  language: "en",
  languages: ["fr", "en"],
  target_duration_seconds: 240,
  quality_profile: "standard",
  production_mode: "technical",
  render_engine: "auto",
  research_enabled: false,
  research_required: true,
  research_max_sources: 10,
  visuals_strategy: "diagrams",
  visuals_allow_stock: false,
  visuals_max_assets: 4,
  captions: "off",
  voice: "auto",
  callback_url: "",
};

// Translate the flat form into the API request, dropping defaults the server
// resolves on its own so the payload stays clean.
export function toRequest(v: FormValues): VideoCreateRequest {
  const body: VideoCreateRequest = {
    prompt: v.prompt.trim(),
    target_duration_seconds: v.target_duration_seconds,
    quality_profile: v.quality_profile,
    production_mode: v.production_mode,
    captions: v.captions,
    research: {
      enabled: v.research_enabled,
      required: v.research_required,
      max_sources: v.research_max_sources,
    },
    visuals: {
      strategy: v.visuals_strategy,
      allow_stock: v.visuals_allow_stock,
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
