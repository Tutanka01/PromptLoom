import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { cn } from "../lib/cn";

// Compact, readable JSON tree. Objects/arrays collapse; primitives are colour-
// coded. Used by the report and artifact viewers, where shapes are free-form.

export function JsonView({ data }: { data: unknown }) {
  return (
    <div className="font-mono text-[12.5px] leading-relaxed">
      <Node value={data} depth={0} defaultOpen />
    </div>
  );
}

function Node({
  name,
  value,
  depth,
  defaultOpen,
}: {
  name?: string;
  value: unknown;
  depth: number;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen ?? depth < 2);
  const isObject = value !== null && typeof value === "object";

  if (!isObject) {
    return (
      <div className="flex gap-2 py-0.5">
        {name !== undefined && <span className="text-muted">{name}:</span>}
        <Scalar value={value} />
      </div>
    );
  }

  const entries = Array.isArray(value)
    ? value.map((v, i) => [String(i), v] as const)
    : Object.entries(value as Record<string, unknown>);
  const summary = Array.isArray(value) ? `[${entries.length}]` : `{${entries.length}}`;

  return (
    <div className={cn(depth > 0 && "border-l border-border pl-3")}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 py-0.5 text-left hover:text-ink"
      >
        <ChevronRight className={cn("size-3.5 text-faint transition-transform", open && "rotate-90")} />
        {name !== undefined && <span className="text-muted">{name}</span>}
        <span className="text-faint">{summary}</span>
      </button>
      {open && (
        <div className="ml-1.5">
          {entries.map(([k, v]) => (
            <Node key={k} name={k} value={v} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

function Scalar({ value }: { value: unknown }) {
  if (value === null) return <span className="text-faint italic">null</span>;
  if (typeof value === "boolean")
    return <span className={value ? "text-success" : "text-danger"}>{String(value)}</span>;
  if (typeof value === "number") return <span className="text-brand-700">{value}</span>;
  const str = String(value);
  return <span className="break-all text-ink">{str.length > 0 ? str : '""'}</span>;
}
