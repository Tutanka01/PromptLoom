// Presentation mapping for job statuses: a short human label and a tone the
// StatusPill / rail colours key off.

import type { JobStatus } from "../api/types";
import { isActive } from "./steps";

export type Tone = "neutral" | "active" | "success" | "danger";

const LABELS: Record<string, string> = {
  queued: "En file",
  waiting_for_master: "En attente",
  planning: "Recherche",
  generating_sources: "Script",
  voice_generation: "Voix",
  render_low_quality: "Rendu brouillon",
  assemble_low_quality: "Assemblage",
  verify_low_quality: "Vérif. brouillon",
  render_final: "Rendu final",
  assemble_final: "Assemblage",
  verify_final: "Contrôles",
  completed: "Terminé",
  cancelled: "Annulé",
  failed_generation: "Échec génération",
  failed_render: "Échec rendu",
  failed_quality: "Échec qualité",
  failed_visual_review: "Échec revue visuelle",
  failed_stale: "Expiré",
};

export function statusLabel(status: JobStatus): string {
  return LABELS[status] ?? status.replace(/_/g, " ");
}

export function statusTone(status: JobStatus): Tone {
  if (status === "completed") return "success";
  if (status === "cancelled") return "neutral";
  if (status.startsWith("failed")) return "danger";
  if (status === "queued" || status === "waiting_for_master") return "neutral";
  return isActive(status) ? "active" : "neutral";
}
