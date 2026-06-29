import { Link } from "react-router-dom";
import { Download, FileText, Layers, Play, X, AlertTriangle } from "lucide-react";
import type { VideoStatus } from "../../api/types";
import { StatusPill } from "../../components/StatusPill";
import { StageRail } from "../../components/StageRail";
import { Chip } from "../../components/ui";
import { cn } from "../../lib/cn";
import { shortId, languageName } from "../../lib/format";
import { prettyStep, isFailed, isActive } from "../../lib/steps";
import { useCancelVideo } from "../../api/queries";
import { api } from "../../api/client";
import { useDownload } from "../../lib/useDownload";

export function JobRow({ job }: { job: VideoStatus }) {
  const cancel = useCancelVideo();
  const { download, pending: downloading } = useDownload();
  const failed = isFailed(job.status);
  const active = isActive(job.status);
  const batch = Boolean(job.batch_id);

  return (
    <div className="group relative rounded-[var(--radius-card)] border border-border bg-surface p-4 transition-colors hover:border-border-strong sm:p-5">
      <Link
        to={`/videos/${job.job_id}`}
        aria-label={`Job ${shortId(job.job_id)}`}
        className="absolute inset-0 rounded-[var(--radius-card)]"
      />

      <div className="relative flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-mono text-[13px] font-medium text-ink">{shortId(job.job_id)}</span>
            {job.language && <Chip>{languageName(job.language)}</Chip>}
            {job.production_mode && <Chip>{job.production_mode}</Chip>}
            {job.render_engine && <Chip>{job.render_engine}</Chip>}
            {batch && (
              <Chip className="bg-brand-50 text-brand-700">
                <Layers className="size-3" /> batch
              </Chip>
            )}
          </div>
        </div>
        <StatusPill status={job.status} />
      </div>

      <div className="relative mt-4 flex items-center gap-3">
        <StageRail status={job.status} className="flex-1" />
        <span className="w-10 shrink-0 text-right font-mono text-xs font-medium text-muted">{job.progress}%</span>
      </div>

      <div className="relative mt-3 flex items-center justify-between gap-3">
        <p
          className={cn(
            "min-w-0 truncate text-[13px]",
            failed ? "text-danger" : "text-muted",
          )}
        >
          {failed && <AlertTriangle className="mr-1 inline size-3.5 -translate-y-px" />}
          {failed ? job.error_message ?? "Échec" : prettyStep(job.current_step)}
        </p>

        <div className="relative z-10 flex shrink-0 items-center gap-1">
          {batch && (
            <ActionLink to={`/batches/${job.batch_id}`} icon={<Layers className="size-4" />} label="Batch" />
          )}
          {job.status === "completed" && (
            <>
              <ActionLink to={`/videos/${job.job_id}`} icon={<Play className="size-4" />} label="Lire" primary />
              <button
                onClick={() => download(api.downloadPath(job.job_id), `${shortId(job.job_id)}-${job.language ?? "video"}.mp4`)}
                disabled={downloading}
                className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border px-2.5 text-[13px] font-medium text-muted transition-colors hover:border-border-strong hover:text-ink disabled:opacity-50"
              >
                <Download className="size-4" /> MP4
              </button>
            </>
          )}
          {job.report_url && (
            <ActionLink to={`/videos/${job.job_id}?tab=report`} icon={<FileText className="size-4" />} label="Rapport" />
          )}
          {active && (
            <button
              onClick={() => cancel.mutate(job.job_id)}
              disabled={cancel.isPending}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border px-2.5 text-[13px] font-medium text-muted transition-colors hover:border-danger hover:bg-danger-50 hover:text-danger disabled:opacity-50"
            >
              <X className="size-4" /> Annuler
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function ActionLink({
  to,
  icon,
  label,
  primary,
}: {
  to: string;
  icon: React.ReactNode;
  label: string;
  primary?: boolean;
}) {
  return (
    <Link
      to={to}
      className={cn(
        "inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-[13px] font-medium transition-colors",
        primary
          ? "bg-brand text-white hover:bg-brand-600"
          : "border border-border text-muted hover:border-border-strong hover:text-ink",
      )}
    >
      {icon} {label}
    </Link>
  );
}
