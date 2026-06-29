import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, FileSearch, FolderOpen } from "lucide-react";
import { api, ApiError } from "../../api/client";
import { Card, Spinner } from "../../components/ui";
import { TextInput } from "../../components/form";
import { JsonView } from "../../components/JsonView";
import { AuthImage } from "../../components/AuthImage";
import { useDownload } from "../../lib/useDownload";
import { cn } from "../../lib/cn";

// Artifacts the pipeline commonly writes (see api-reference.md / operations).
const SUGGESTED = [
  "blueprint.json",
  "research.json",
  "proposal.json",
  "scene_plan.json",
  "asset_manifest.json",
  "motion_plan_report.json",
  "logs/render-final.log",
  "logs/render-low.log",
];

const isImage = (p: string) => /\.(png|jpe?g|webp|gif)$/i.test(p);
const isJson = (p: string) => /\.json$/i.test(p);

export function ArtifactsTab({ jobId }: { jobId: string }) {
  const [path, setPath] = useState<string>("blueprint.json");
  const [draft, setDraft] = useState<string>("blueprint.json");
  const { download } = useDownload();

  return (
    <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
      <Card className="h-fit px-4 py-4">
        <p className="mb-3 flex items-center gap-1.5 text-xs font-medium tracking-wide text-faint uppercase">
          <FolderOpen className="size-3.5" /> Artefacts
        </p>
        <div className="flex flex-col gap-1">
          {SUGGESTED.map((p) => (
            <button
              key={p}
              onClick={() => {
                setPath(p);
                setDraft(p);
              }}
              className={cn(
                "truncate rounded-md px-2.5 py-1.5 text-left font-mono text-[12.5px] transition-colors",
                path === p ? "bg-brand-50 text-brand-700" : "text-muted hover:bg-surface-2 hover:text-ink",
              )}
            >
              {p}
            </button>
          ))}
        </div>
        <form
          className="mt-3 border-t border-border pt-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (draft.trim()) setPath(draft.trim().replace(/^\/+/, ""));
          }}
        >
          <TextInput
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="chemin/libre.ext"
            className="font-mono text-xs"
            aria-label="Chemin d'artefact"
          />
        </form>
      </Card>

      <div className="min-w-0">
        <div className="mb-3 flex items-center justify-between gap-3">
          <code className="truncate rounded-md bg-inset px-2 py-1 font-mono text-xs text-muted">{path}</code>
          <button
            onClick={() => download(api.artifactPath(jobId, path), path.split("/").pop() ?? "artifact")}
            className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg border border-border px-2.5 text-[13px] font-medium text-muted transition-colors hover:border-border-strong hover:text-ink"
          >
            <Download className="size-4" /> Télécharger
          </button>
        </div>
        <ArtifactViewer jobId={jobId} path={path} />
      </div>
    </div>
  );
}

function ArtifactViewer({ jobId, path }: { jobId: string; path: string }) {
  if (isImage(path)) {
    return (
      <Card className="overflow-hidden p-3">
        <AuthImage path={api.artifactPath(jobId, path)} alt={path} className="w-full rounded-lg" />
      </Card>
    );
  }
  return <TextArtifact jobId={jobId} path={path} />;
}

function TextArtifact({ jobId, path }: { jobId: string; path: string }) {
  const q = useQuery({
    queryKey: ["artifact", jobId, path],
    queryFn: () => api.fetchArtifactText(jobId, path),
    retry: false,
  });

  if (q.isLoading)
    return (
      <Card className="flex justify-center py-16">
        <Spinner />
      </Card>
    );
  if (q.isError)
    return (
      <Card className="flex flex-col items-center gap-2 py-16 text-center text-sm text-muted">
        <FileSearch className="size-7 text-faint" />
        {q.error instanceof ApiError && q.error.status === 404 ? "Artefact introuvable." : "Lecture impossible."}
      </Card>
    );

  const text = q.data ?? "";
  if (isJson(path)) {
    try {
      return (
        <Card className="max-h-[560px] overflow-auto px-4 py-4">
          <JsonView data={JSON.parse(text)} />
        </Card>
      );
    } catch {
      // fall through to raw text
    }
  }
  return (
    <Card className="max-h-[560px] overflow-auto">
      <pre className="p-4 font-mono text-[12.5px] leading-relaxed whitespace-pre-wrap text-ink">{text}</pre>
    </Card>
  );
}
