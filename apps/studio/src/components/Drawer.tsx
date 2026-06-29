// Right-side slide-over. Closes on Escape and backdrop click. Locks body
// scroll while open.

import { useEffect, type ReactNode } from "react";
import { X } from "lucide-react";
import { IconButton } from "./ui";

export function Drawer({
  open,
  onClose,
  title,
  children,
  width = "max-w-md",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  width?: string;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40" role="dialog" aria-modal="true" aria-label={title}>
      <div
        className="absolute inset-0 bg-ink/30 backdrop-blur-[2px] animate-[fade-up_0.2s_ease]"
        onClick={onClose}
      />
      <div
        className={`absolute top-0 right-0 flex h-full w-full ${width} flex-col border-l border-border bg-surface shadow-[0_0_60px_-15px_rgba(12,19,34,0.4)]`}
        style={{ animation: "fade-up 0.28s cubic-bezier(0.16,1,0.3,1)" }}
      >
        <header className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="font-display text-lg font-medium">{title}</h2>
          <IconButton label="Fermer" onClick={onClose}>
            <X className="size-4" />
          </IconButton>
        </header>
        <div className="flex-1 overflow-y-auto p-5">{children}</div>
      </div>
    </div>
  );
}
