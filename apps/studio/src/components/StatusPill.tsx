import { cn } from "../lib/cn";
import type { JobStatus } from "../api/types";
import { statusLabel, statusTone, type Tone } from "../lib/status";

const TONE_STYLES: Record<Tone, string> = {
  neutral: "bg-surface-2 text-muted",
  active: "bg-brand-50 text-brand-700",
  success: "bg-success-50 text-success",
  danger: "bg-danger-50 text-danger",
};

export function StatusPill({ status, className }: { status: JobStatus; className?: string }) {
  const tone = statusTone(status);
  const active = tone === "active";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium whitespace-nowrap",
        TONE_STYLES[tone],
        className,
      )}
    >
      <span
        className={cn(
          "size-1.5 rounded-full bg-current",
          active && "animate-rail-pulse",
        )}
      />
      {statusLabel(status)}
    </span>
  );
}
