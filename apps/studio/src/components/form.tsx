// Themed form controls. Bare, hairline-bordered, brand focus ring.

import type {
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";
import { cn } from "../lib/cn";

const baseField =
  "w-full rounded-lg border border-border bg-surface px-3 text-sm text-ink placeholder:text-faint transition-colors hover:border-border-strong focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/25";

export function Field({
  label,
  htmlFor,
  hint,
  error,
  children,
}: {
  label: string;
  htmlFor?: string;
  hint?: ReactNode;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-sm font-medium text-ink">
        {label}
      </label>
      {children}
      {error ? (
        <p className="text-xs text-danger">{error}</p>
      ) : hint ? (
        <p className="text-xs text-muted">{hint}</p>
      ) : null}
    </div>
  );
}

export function TextInput({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(baseField, "h-10", className)} {...props} />;
}

export function TextArea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(baseField, "resize-y py-2.5 leading-relaxed", className)} {...props} />;
}

export function Select({
  className,
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cn(baseField, "h-10 appearance-none bg-no-repeat pr-9", className)} {...props}>
      {children}
    </select>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  description,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  description?: string;
}) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-4">
      <span className="flex flex-col">
        <span className="text-sm font-medium text-ink">{label}</span>
        {description ? <span className="text-xs text-muted">{description}</span> : null}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative mt-0.5 h-6 w-10 shrink-0 rounded-full transition-colors",
          checked ? "bg-brand" : "bg-surface-2 ring-1 ring-inset ring-border-strong",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 left-0.5 size-5 rounded-full bg-white shadow-sm transition-transform",
            checked && "translate-x-4",
          )}
        />
      </button>
    </label>
  );
}

export interface SegOption<T extends string> {
  value: T;
  label: string;
  hint?: string;
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  disabledValues,
}: {
  options: SegOption<T>[];
  value: T;
  onChange: (v: T) => void;
  disabledValues?: T[];
}) {
  return (
    <div className="grid auto-cols-fr grid-flow-col gap-1 rounded-lg border border-border bg-inset p-1">
      {options.map((opt) => {
        const active = opt.value === value;
        const disabled = disabledValues?.includes(opt.value) ?? false;
        return (
          <button
            key={opt.value}
            type="button"
            disabled={disabled}
            title={opt.hint}
            onClick={() => onChange(opt.value)}
            className={cn(
              "rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors",
              active ? "bg-surface text-ink shadow-sm ring-1 ring-border" : "text-muted hover:text-ink",
              disabled && "cursor-not-allowed opacity-40 hover:text-muted",
            )}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

export function RangeField({
  value,
  onChange,
  min,
  max,
  step = 1,
  readout,
}: {
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step?: number;
  readout: string;
}) {
  return (
    <div className="flex items-center gap-4">
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-1.5 flex-1 cursor-pointer appearance-none rounded-full bg-surface-2 accent-brand"
      />
      <span className="w-20 shrink-0 text-right font-mono text-sm font-medium text-ink">{readout}</span>
    </div>
  );
}
