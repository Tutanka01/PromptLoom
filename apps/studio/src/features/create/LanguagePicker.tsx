import { Star } from "lucide-react";
import { cn } from "../../lib/cn";
import type { LanguageOption } from "../../lib/capabilities";

// Ordered multi-select over the languages the deployment can actually speak
// (GET /v1/capabilities). Click to append, click again to remove. The first
// selected language is the batch primary (it generates the master blueprint).
export function LanguagePicker({
  options,
  value,
  onChange,
  max = 8,
}: {
  options: LanguageOption[];
  value: string[];
  onChange: (next: string[]) => void;
  max?: number;
}) {
  function toggle(code: string) {
    if (value.includes(code)) {
      onChange(value.filter((c) => c !== code));
    } else if (value.length < max) {
      onChange([...value, code]);
    }
  }

  return (
    <div>
      <div className="flex flex-wrap gap-1.5">
        {options.map((lang) => {
          const index = value.indexOf(lang.code);
          const selected = index >= 0;
          const primary = index === 0;
          const atCap = !selected && value.length >= max;
          return (
            <button
              key={lang.code}
              type="button"
              disabled={atCap}
              onClick={() => toggle(lang.code)}
              aria-pressed={selected}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[13px] font-medium transition-colors",
                selected
                  ? "border-brand bg-brand-50 text-brand-700"
                  : "border-border bg-surface text-muted hover:border-border-strong hover:text-ink",
                atCap && "cursor-not-allowed opacity-40",
              )}
            >
              {selected && (
                <span className="flex min-w-4 items-center justify-center font-mono text-[11px]">
                  {primary ? <Star className="size-3 fill-current" /> : index + 1}
                </span>
              )}
              {lang.name}
            </button>
          );
        })}
      </div>
      <p className="mt-2 text-xs text-muted">
        {value.length} / {max} · la première langue{" "}
        <Star className="inline size-3 -translate-y-px fill-brand text-brand" /> est la primaire (elle
        génère le blueprint maître ; les autres le traduisent).
      </p>
    </div>
  );
}
