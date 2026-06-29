import { useParams, Link } from "react-router-dom";
import { ArrowLeft, Download, Layers, Play, Star } from "lucide-react";
import { useBatch } from "../../api/queries";
import { api, ApiError } from "../../api/client";
import type { VideoStatus } from "../../api/types";
import { Card, Chip, EmptyState, Spinner } from "../../components/ui";
import { StatusPill } from "../../components/StatusPill";
import { StageRail } from "../../components/StageRail";
import { useDownload } from "../../lib/useDownload";
import { shortId, languageName } from "../../lib/format";
import { prettyStep, isFailed } from "../../lib/steps";

export function BatchPage() {
  const { batchId } = useParams<{ batchId: string }>();
  const query = useBatch(batchId);

  if (query.isLoading)
    return (
      <div className="flex justify-center py-24">
        <Spinner />
      </div>
    );
  if (query.isError || !query.data)
    return (
      <EmptyState
        title="Batch introuvable"
        children={
          query.error instanceof ApiError && query.error.status === 401
            ? "Authentification requise — ajoute ta clé dans Réglages."
            : "Aucune vidéo ne porte cet identifiant de batch."
        }
      />
    );

  const batch = query.data;

  return (
    <div className="animate-fade-up">
      <Link to="/" className="mb-5 inline-flex items-center gap-1.5 text-sm text-muted transition-colors hover:text-ink">
        <ArrowLeft className="size-4" /> Tableau de bord
      </Link>

      <div className="mb-6 flex items-center gap-3">
        <span className="flex size-10 items-center justify-center rounded-xl bg-brand-50 text-brand">
          <Layers className="size-5" />
        </span>
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Batch multilingue</h1>
          <p className="text-sm text-muted">
            <span className="font-mono">{shortId(batch.batch_id)}</span> · {batch.languages.length} langues · contenu
            identique, narration traduite
          </p>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {batch.jobs.map((job, index) => (
          <BatchJobCard key={job.job_id} job={job} isPrimary={index === 0} />
        ))}
      </div>
    </div>
  );
}

function BatchJobCard({ job, isPrimary }: { job: VideoStatus; isPrimary: boolean }) {
  const { download, pending } = useDownload();
  const failed = isFailed(job.status);

  return (
    <Card className="flex flex-col gap-4 p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="font-display text-lg font-medium text-ink">{languageName(job.language)}</span>
          {isPrimary && (
            <Chip className="bg-brand-50 text-brand-700">
              <Star className="size-3 fill-current" /> primaire
            </Chip>
          )}
        </div>
        <StatusPill status={job.status} />
      </div>

      <div className="flex items-center gap-3">
        <StageRail status={job.status} className="flex-1" />
        <span className="w-10 text-right font-mono text-xs font-medium text-muted">{job.progress}%</span>
      </div>

      <p className="font-mono text-[12px] text-faint">
        {shortId(job.job_id)} · {failed ? job.error_message ?? "échec" : prettyStep(job.current_step)}
      </p>

      <div className="flex items-center gap-2">
        <Link
          to={`/videos/${job.job_id}`}
          className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-border px-3 text-[13px] font-medium text-muted transition-colors hover:border-border-strong hover:text-ink"
        >
          <Play className="size-4" /> Ouvrir
        </Link>
        {job.status === "completed" && (
          <button
            onClick={() => download(api.downloadPath(job.job_id), `${shortId(job.job_id)}-${job.language ?? "video"}.mp4`)}
            disabled={pending}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-brand px-3 text-[13px] font-medium text-white transition-colors hover:bg-brand-600 disabled:opacity-50"
          >
            <Download className="size-4" /> MP4
          </button>
        )}
      </div>
    </Card>
  );
}
