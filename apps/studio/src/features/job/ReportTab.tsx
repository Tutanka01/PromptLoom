import { useQuery } from "@tanstack/react-query";
import { Download, FileJson } from "lucide-react";
import { api } from "../../api/client";
import type { VideoReport } from "../../api/types";
import { Card, Spinner, EmptyState } from "../../components/ui";
import { JsonView } from "../../components/JsonView";
import { AuthImage } from "../../components/AuthImage";
import { useDownload } from "../../lib/useDownload";
import { formatDuration } from "../../lib/format";

function findPngPaths(node: unknown, out: string[] = [], depth = 0): string[] {
  if (depth > 6 || out.length > 24) return out;
  if (typeof node === "string") {
    if (/\.png$/i.test(node)) out.push(node.replace(/^\/+/, ""));
  } else if (Array.isArray(node)) {
    for (const v of node) findPngPaths(v, out, depth + 1);
  } else if (node && typeof node === "object") {
    for (const v of Object.values(node)) findPngPaths(v, out, depth + 1);
  }
  return out;
}

function asNumber(v: unknown): number | undefined {
  return typeof v === "number" ? v : undefined;
}

export function ReportTab({ jobId }: { jobId: string }) {
  const report = useQuery({ queryKey: ["report", jobId], queryFn: () => api.getReport(jobId) });
  const { download } = useDownload();

  if (report.isLoading)
    return (
      <div className="flex justify-center py-16">
        <Spinner />
      </div>
    );
  if (report.isError || !report.data)
    return <EmptyState icon={<FileJson className="size-9" strokeWidth={1.5} />} title="Rapport indisponible" />;

  const data = report.data as VideoReport;
  const duration = asNumber(data.duration) ?? asNumber(data.duration_seconds);
  const snapshots = [...new Set(findPngPaths(data))];
  const subtitles = (data.subtitles ?? {}) as { srt?: string; vtt?: string };

  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Metric label="Durée" value={duration ? formatDuration(duration) : "—"} />
        <Metric label="Profil" value={(data.quality_profile as string) ?? "—"} />
        <Metric label="Snapshots" value={`${snapshots.length}`} />
        <Metric
          label="Sous-titres"
          value={subtitles.srt || subtitles.vtt ? "présents" : "aucun"}
        />
      </div>

      {(subtitles.srt || subtitles.vtt) && (
        <Card className="px-5 py-4">
          <p className="mb-3 text-sm font-medium text-ink">Sous-titres</p>
          <div className="flex gap-2">
            {(["srt", "vtt"] as const).map((ext) =>
              subtitles[ext] ? (
                <button
                  key={ext}
                  onClick={() => download(api.artifactPath(jobId, subtitles[ext]!), `${jobId.slice(0, 8)}.${ext}`)}
                  className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-border px-3 text-[13px] font-medium text-muted transition-colors hover:border-border-strong hover:text-ink"
                >
                  <Download className="size-4" /> .{ext}
                </button>
              ) : null,
            )}
          </div>
        </Card>
      )}

      {snapshots.length > 0 && (
        <Card className="px-5 py-4">
          <p className="mb-3 text-sm font-medium text-ink">Snapshots de contrôle</p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {snapshots.slice(0, 9).map((path) => (
              <AuthImage
                key={path}
                path={api.artifactPath(jobId, path)}
                alt={path}
                className="aspect-video w-full rounded-lg border border-border object-cover"
              />
            ))}
          </div>
        </Card>
      )}

      <Card className="px-5 py-4">
        <p className="mb-3 text-sm font-medium text-ink">Rapport complet</p>
        <div className="max-h-[480px] overflow-auto rounded-lg bg-inset p-4">
          <JsonView data={data} />
        </div>
      </Card>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-surface-2 px-4 py-3">
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-1 truncate font-display text-lg font-medium text-ink">{value}</p>
    </div>
  );
}
