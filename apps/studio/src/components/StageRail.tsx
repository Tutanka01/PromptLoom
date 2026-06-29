// The signature element. A job's progress rendered as an editing-console
// transport: the pipeline's stages, the active one lit and "flowing" while the
// worker runs, the rest filled or idle. Faithful to lib/steps STAGES.

import { Check, X } from "lucide-react";
import { cn } from "../lib/cn";
import type { JobStatus } from "../api/types";
import { STAGES, isFailed, stageIndexForStatus } from "../lib/steps";

type SegState = "done" | "active" | "failed" | "idle";

function segStates(status: JobStatus): SegState[] {
  const current = stageIndexForStatus(status);
  const failed = isFailed(status);
  const completed = status === "completed";
  const cancelled = status === "cancelled";
  return STAGES.map((_, i) => {
    if (cancelled) return i < current ? "done" : "idle";
    if (completed) return "done";
    if (failed) {
      if (i < current) return "done";
      if (i === current) return "failed";
      return "idle";
    }
    if (i < current) return "done";
    if (i === current) return "active";
    return "idle";
  });
}

const FLOW_STRIPES =
  "repeating-linear-gradient(115deg, var(--color-brand) 0 6px, var(--color-brand-600) 6px 12px)";

// Compact rail for dashboard cards: one slim segment per pipeline stage.
export function StageRail({ status, className }: { status: JobStatus; className?: string }) {
  const states = segStates(status);
  return (
    <div className={cn("flex items-center gap-1", className)} aria-hidden="true">
      {states.map((state, i) => (
        <div
          key={STAGES[i].id}
          className={cn(
            "h-1.5 flex-1 rounded-full transition-colors",
            state === "done" && (status === "completed" ? "bg-success" : "bg-brand"),
            state === "failed" && "bg-danger",
            state === "idle" && "bg-surface-2",
          )}
          style={
            state === "active"
              ? {
                  backgroundImage: FLOW_STRIPES,
                  backgroundSize: "16px 16px",
                  animation: "var(--animate-rail-flow)",
                }
              : undefined
          }
        />
      ))}
    </div>
  );
}

// Full labelled transport for the job detail page.
export function StageRailFull({ status }: { status: JobStatus }) {
  const states = segStates(status);
  const completed = status === "completed";
  const last = STAGES.length - 1;
  const reach = completed ? last : Math.max(0, Math.min(stageIndexForStatus(status), last));
  const fraction = last === 0 ? 1 : reach / last;

  return (
    <div className="relative px-2">
      <div className="absolute top-4 right-6 left-6 h-0.5 rounded-full bg-border" />
      <div
        className="absolute top-4 left-6 h-0.5 rounded-full bg-brand transition-[width] duration-500"
        style={{ width: `calc((100% - 3rem) * ${fraction})` }}
      />
      <ol className="relative flex justify-between">
        {STAGES.map((stage, i) => {
          const state = states[i];
          const filled = state === "done" || completed;
          return (
            <li key={stage.id} className="flex flex-col items-center gap-2">
              <span
                className={cn(
                  "relative flex size-8 items-center justify-center rounded-full border-2 bg-surface text-xs font-medium transition-colors",
                  filled && "border-brand bg-brand text-white",
                  state === "active" && "border-brand text-brand",
                  state === "failed" && "border-danger bg-danger text-white",
                  state === "idle" && "border-border-strong text-faint",
                )}
              >
                {state === "active" && (
                  <span className="absolute inset-[-3px] animate-rail-pulse rounded-full ring-2 ring-brand/40" />
                )}
                {filled ? (
                  <Check className="size-4" strokeWidth={2.5} />
                ) : state === "failed" ? (
                  <X className="size-4" strokeWidth={2.5} />
                ) : (
                  i + 1
                )}
              </span>
              <span
                className={cn(
                  "font-mono text-[11px] tracking-tight",
                  state === "active" ? "font-medium text-brand-700" : "text-muted",
                )}
              >
                {stage.label}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
