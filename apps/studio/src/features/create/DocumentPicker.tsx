import { useRef, useState, type DragEvent } from "react";
import { FileText, FileUp, TriangleAlert, X } from "lucide-react";
import { AuthImage } from "../../components/AuthImage";
import { IconButton, Spinner } from "../../components/ui";
import { useUploadDocument } from "../../api/queries";
import { ApiError } from "../../api/client";
import type { DocumentResponse } from "../../api/types";
import { cn } from "../../lib/cn";

const MAX_THUMBS = 8;

// Optional PDF source. Upload runs the server-side extraction right away, so the
// card can show what the video will actually be able to use: the detected
// sections and the figures that FigureScene can put on screen.
export function DocumentPicker({
  value,
  onChange,
  onError,
}: {
  value: DocumentResponse | null;
  onChange: (doc: DocumentResponse | null) => void;
  onError: (message: string) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const upload = useUploadDocument();
  const [dragging, setDragging] = useState(false);

  function send(file: File | undefined) {
    if (!file) return;
    if (file.type && file.type !== "application/pdf") {
      onError("Seuls les fichiers PDF sont acceptés.");
      return;
    }
    upload.mutate(file, {
      onSuccess: (doc) => onChange(doc),
      onError: (err) => onError(err instanceof ApiError ? err.message : "L'analyse du PDF a échoué."),
    });
  }

  function onDrop(event: DragEvent<HTMLButtonElement>) {
    event.preventDefault();
    setDragging(false);
    send(event.dataTransfer.files?.[0]);
  }

  if (value) {
    const extra = value.figures.length - MAX_THUMBS;
    return (
      <div className="rounded-xl border border-border bg-surface-2 p-4">
        <div className="flex items-start gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand">
            <FileText className="size-4.5" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-ink" title={value.title}>
              {value.title}
            </p>
            <p className="mt-0.5 truncate font-mono text-[11px] text-faint">
              {value.filename} · {value.page_count} p. · {value.sections.length} sections ·{" "}
              {value.figures.length} figure{value.figures.length > 1 ? "s" : ""}
            </p>
          </div>
          <IconButton label="Retirer le document" onClick={() => onChange(null)} type="button">
            <X className="size-4" />
          </IconButton>
        </div>
        {value.figures.length > 0 ? (
          <div className="mt-3 grid grid-cols-4 gap-2">
            {value.figures.slice(0, MAX_THUMBS).map((fig) => (
              <figure key={fig.id} className="overflow-hidden rounded-lg border border-border bg-white" title={fig.caption}>
                <AuthImage path={fig.image_url} alt={fig.label} className="h-20 w-full object-contain" />
                <figcaption className="truncate border-t border-border bg-surface px-1.5 py-0.5 text-[10px] text-muted">
                  {fig.label} · p. {fig.page}
                </figcaption>
              </figure>
            ))}
            {extra > 0 ? (
              <div className="flex h-full min-h-20 items-center justify-center rounded-lg border border-dashed border-border text-xs text-muted">
                +{extra}
              </div>
            ) : null}
          </div>
        ) : null}
        {value.warnings.length > 0 ? (
          <ul className="mt-3 flex flex-col gap-1">
            {value.warnings.map((warning) => (
              <li key={warning} className="flex items-start gap-1.5 text-xs text-amber">
                <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
                {warning}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    );
  }

  return (
    <>
      <input
        ref={input}
        type="file"
        accept="application/pdf,.pdf"
        className="hidden"
        onChange={(event) => {
          send(event.target.files?.[0]);
          event.target.value = "";
        }}
      />
      <button
        type="button"
        disabled={upload.isPending}
        onClick={() => input.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          "flex w-full items-center justify-center gap-2.5 rounded-xl border border-dashed px-4 py-5 text-sm transition-colors",
          dragging ? "border-brand bg-brand-50 text-brand" : "border-border text-muted hover:border-border-strong hover:text-ink",
        )}
      >
        {upload.isPending ? (
          <>
            <Spinner className="size-4" /> Analyse du PDF (texte et figures)…
          </>
        ) : (
          <>
            <FileUp className="size-4" /> Déposer un PDF ou cliquer pour choisir (article, cours, rapport…)
          </>
        )}
      </button>
    </>
  );
}
