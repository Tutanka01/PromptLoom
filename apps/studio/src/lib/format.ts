// Small formatting helpers shared across views.

export function shortId(id: string): string {
  return id.slice(0, 8);
}

export function formatDuration(seconds?: number | null): string {
  if (!seconds && seconds !== 0) return "—";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  if (m === 0) return `${s}s`;
  return `${m}m${s.toString().padStart(2, "0")}`;
}

export function formatBytes(bytes?: number | null): string {
  if (!bytes && bytes !== 0) return "—";
  const units = ["o", "Ko", "Mo", "Go"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value < 10 && unit > 0 ? 1 : 0)} ${units[unit]}`;
}

const LANGUAGE_NAMES: Record<string, string> = {
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
  ja: "Japonais",
  ko: "Coréen",
  ms: "Malais",
  fa: "Persan",
  sw: "Swahili",
  tl: "Tagalog",
  th: "Thaï",
  vi: "Vietnamien",
};

export function languageName(code?: string | null): string {
  if (!code) return "—";
  return LANGUAGE_NAMES[code] ?? code.toUpperCase();
}

export function titleFromPrompt(prompt: string, max = 90): string {
  const clean = prompt.replace(/\s+/g, " ").trim();
  if (clean.length <= max) return clean;
  return clean.slice(0, max).replace(/\s\S*$/, "") + "…";
}
