// Normalizes GET /v1/capabilities into the shape the create form consumes.
// The form never hardcodes what the deployment supports: languages come from
// the effective TTS engine per profile, features (research, stock media,
// visual review) from the configured providers, limits from the API contract.
// An older API without the endpoint gets a permissive fallback mirroring the
// server's own built-in contract, so the form still works — it just can't
// grey out what the deployment lacks.

import type {
  CapabilitiesResponse,
  CaptionMode,
  ProductionMode,
  QualityProfile,
  RenderEngine,
  VoiceEngine,
} from "../api/types";

export interface LanguageOption {
  code: string;
  name: string;
}

export interface Range {
  min: number;
  max: number;
  default: number;
}

export interface EffectiveCaps {
  // False while loading or when the API predates /v1/capabilities.
  fromServer: boolean;
  engineByProfile: Record<string, VoiceEngine>;
  // Every language the API accepts, ordered for display (FR labels).
  languages: LanguageOption[];
  languagesByProfile: Record<string, string[]>;
  renderEngines: RenderEngine[];
  research: { available: boolean; provider: string | null };
  stockAssets: { available: boolean; provider: string | null };
  visualReview: { available: boolean };
  limits: {
    promptMaxChars: number;
    themeMaxChars: number;
    maxBatchLanguages: number;
    duration: Range;
    researchMaxSources: Range;
    visualsMaxAssets: Range;
  };
  defaults: {
    productionMode: ProductionMode;
    captionMode: CaptionMode;
    qualityProfile: QualityProfile;
    renderEngine: RenderEngine;
  };
}

// French display names; codes the server advertises that we don't know keep
// the server-provided (English) name.
const FRENCH_LANGUAGE_NAMES: Record<string, string> = {
  en: "Anglais",
  fr: "Français",
  es: "Espagnol",
  it: "Italien",
  pt: "Portugais",
  de: "Allemand",
  nl: "Néerlandais",
  ro: "Roumain",
  pl: "Polonais",
  cs: "Tchèque",
  da: "Danois",
  sv: "Suédois",
  fi: "Finnois",
  el: "Grec",
  hu: "Hongrois",
  mk: "Macédonien",
  ru: "Russe",
  tr: "Turc",
  zh: "Chinois",
  yue: "Cantonais",
  ar: "Arabe",
  he: "Hébreu",
  hi: "Hindi",
  ms: "Malais",
  fa: "Persan",
  sw: "Swahili",
  tl: "Tagalog",
  th: "Thaï",
  vi: "Vietnamien",
};

// Display order: common European targets first, then the rest.
const PREFERRED_ORDER = [
  "fr", "en", "es", "de", "it", "pt", "nl", "ro", "pl", "cs", "da", "sv", "fi", "el", "hu",
];

// Mirror of languages.py SUPPORTED_LANGUAGES, used only when the API has no
// /v1/capabilities endpoint.
const FALLBACK_LANGUAGE_CODES = Object.keys(FRENCH_LANGUAGE_NAMES);

const QUALITY_PROFILES = ["draft", "standard", "high", "final"] as const;

function orderLanguages(options: LanguageOption[]): LanguageOption[] {
  const rank = (code: string) => {
    const index = PREFERRED_ORDER.indexOf(code);
    return index === -1 ? PREFERRED_ORDER.length : index;
  };
  return [...options].sort(
    (a, b) => rank(a.code) - rank(b.code) || a.name.localeCompare(b.name, "fr"),
  );
}

const FALLBACK_CAPS: EffectiveCaps = {
  fromServer: false,
  engineByProfile: {},
  languages: orderLanguages(
    FALLBACK_LANGUAGE_CODES.map((code) => ({ code, name: FRENCH_LANGUAGE_NAMES[code] })),
  ),
  languagesByProfile: Object.fromEntries(
    QUALITY_PROFILES.map((profile) => [profile, FALLBACK_LANGUAGE_CODES]),
  ),
  renderEngines: ["manim", "remotion"],
  // Without capability data we cannot grey anything out: stay permissive and
  // let the server enforce.
  research: { available: true, provider: null },
  stockAssets: { available: true, provider: null },
  visualReview: { available: true },
  limits: {
    promptMaxChars: 4000,
    themeMaxChars: 80,
    maxBatchLanguages: 8,
    duration: { min: 20, max: 900, default: 240 },
    researchMaxSources: { min: 3, max: 20, default: 10 },
    visualsMaxAssets: { min: 0, max: 12, default: 4 },
  },
  defaults: {
    productionMode: "technical",
    captionMode: "off",
    qualityProfile: "standard",
    renderEngine: "manim",
  },
};

export function normalizeCaps(data: CapabilitiesResponse | undefined): EffectiveCaps {
  if (!data) return FALLBACK_CAPS;
  return {
    fromServer: true,
    engineByProfile: data.engine_by_profile,
    languages: orderLanguages(
      data.languages.map((lang) => ({
        code: lang.code,
        name: FRENCH_LANGUAGE_NAMES[lang.code] ?? lang.name,
      })),
    ),
    languagesByProfile: data.languages_by_profile,
    renderEngines: data.render_engines,
    research: data.features.research,
    stockAssets: data.features.stock_assets,
    visualReview: { available: data.features.visual_review.available },
    limits: {
      promptMaxChars: data.limits.prompt_max_chars,
      themeMaxChars: data.limits.theme_max_chars,
      maxBatchLanguages: data.limits.max_batch_languages,
      duration: data.limits.target_duration_seconds,
      researchMaxSources: data.limits.research_max_sources,
      visualsMaxAssets: data.limits.visuals_max_assets,
    },
    defaults: {
      productionMode: data.defaults.production_mode,
      captionMode: data.defaults.caption_mode,
      qualityProfile: data.defaults.quality_profile,
      renderEngine: data.defaults.render_engine,
    },
  };
}

/** Languages allowed for a profile, as displayable options. */
export function allowedLanguages(caps: EffectiveCaps, profile: QualityProfile): LanguageOption[] {
  const codes = caps.languagesByProfile[profile];
  if (!codes) return caps.languages;
  const set = new Set(codes);
  return caps.languages.filter((lang) => set.has(lang.code));
}

/** Human label for a TTS engine family. */
export function engineLabel(engine: VoiceEngine | undefined): string {
  switch (engine) {
    case "kokoro":
      return "Kokoro";
    case "moss":
      return "MOSS";
    case "openai":
      return "OpenAI TTS";
    case "chatterbox":
      return "Chatterbox";
    default:
      return engine ?? "serveur";
  }
}
