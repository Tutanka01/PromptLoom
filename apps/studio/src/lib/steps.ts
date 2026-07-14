// The Stage Rail model. Maps the worker's `status` (which walks the pipeline,
// see production.py `_update`) onto a fixed, human-readable transport of stages.
// The rail is the app's signature element, so this mapping is its source of
// truth — keep it faithful to the real pipeline.

import type { JobStatus } from "../api/types";

export interface Stage {
  id: string;
  label: string;
  // Progress value at which this stage is reached, used to fill the rail.
  at: number;
}

// Six stages + an implicit "done" terminus. Ordered, with the canonical
// progress mark the worker emits when it enters each.
export const STAGES: Stage[] = [
  { id: "queued", label: "File", at: 0 },
  { id: "research", label: "Recherche", at: 3 },
  { id: "script", label: "Script", at: 26 },
  { id: "voice", label: "Voix", at: 40 },
  { id: "render", label: "Rendu", at: 55 },
  { id: "verify", label: "Contrôles", at: 92 },
];

const STATUS_TO_STAGE: Record<string, string> = {
  queued: "queued",
  waiting_for_master: "queued",
  planning: "research",
  generating_sources: "script",
  voice_generation: "voice",
  render_final: "render",
  assemble_final: "render",
  // The visual review now runs on the final assembled MP4 (after render/assemble,
  // before verify); it still belongs to the "render" stage on the rail.
  visual_review: "render",
  verify_final: "verify",
  // Legacy statuses from historical jobs still in the DB (the low-quality proxy
  // render was removed; review now inspects the final render). Keep them mapped.
  render_low_quality: "render",
  assemble_low_quality: "render",
  verify_low_quality: "render",
  completed: "verify",
};

const TERMINAL = new Set<string>([
  "completed",
  "cancelled",
  "failed_generation",
  "failed_render",
  "failed_quality",
  "failed_visual_review",
  "failed_stale",
]);

// Which stage a failure halts at, so the rail can show where it broke.
const FAILURE_STAGE: Record<string, string> = {
  failed_generation: "script",
  failed_render: "render",
  failed_quality: "verify",
  failed_visual_review: "verify",
  failed_stale: "queued",
};

export function isTerminal(status: JobStatus): boolean {
  return TERMINAL.has(status);
}

export function isFailed(status: JobStatus): boolean {
  return status.startsWith("failed");
}

export function isActive(status: JobStatus): boolean {
  return !isTerminal(status);
}

export function stageIndexForStatus(status: JobStatus): number {
  if (status === "completed") return STAGES.length; // past the last stage
  if (isFailed(status)) {
    const id = FAILURE_STAGE[status] ?? "queued";
    return STAGES.findIndex((s) => s.id === id);
  }
  if (status === "cancelled") return -1;
  const id = STATUS_TO_STAGE[status] ?? "queued";
  return STAGES.findIndex((s) => s.id === id);
}

// Granular step labels the worker writes to `current_step`, prettified for the
// detail header (e.g. "render_final" -> "Rendu final").
const STEP_LABELS: Record<string, string> = {
  queued: "En file",
  waiting_for_master: "En attente du master",
  researching: "Recherche des sources",
  planning: "Planification",
  scene_codegen: "Génération des scènes",
  generating_sources: "Génération des sources",
  voice_generation: "Synthèse vocale",
  render_final: "Rendu final",
  assemble_final: "Assemblage final",
  visual_review: "Revue visuelle",
  verify_final: "Vérification finale",
  // Legacy steps from historical jobs (low-quality proxy render removed).
  render_low_quality: "Rendu brouillon",
  assemble_low_quality: "Assemblage brouillon",
  verify_low_quality: "Vérification brouillon",
  completed: "Terminé",
};

export function prettyStep(step?: string | null): string {
  if (!step) return "—";
  return STEP_LABELS[step] ?? step.replace(/_/g, " ");
}
