import { useParams, useSearchParams, Link } from "react-router-dom";
import { ArrowLeft, Download, Layers, X, AlertTriangle, Ban, Wrench } from "lucide-react";
import { useVideo, useCancelVideo } from "../../api/queries";
import { api, ApiError } from "../../api/client";
import { Button, Card, Chip, EmptyState, Spinner } from "../../components/ui";
import { StatusPill } from "../../components/StatusPill";
import { StageRailFull } from "../../components/StageRail";
import { useToast } from "../../components/Toast";
import { useDownload } from "../../lib/useDownload";
import { shortId, languageName } from "../../lib/format";
import { prettyStep, isFailed, isActive } from "../../lib/steps";
import { VideoPlayer } from "./VideoPlayer";
import { ReportTab } from "./ReportTab";
import { ArtifactsTab } from "./ArtifactsTab";
import { cn } from "../../lib/cn";

type Tab = "overview" | "report" | "artifacts";

export function JobPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) || "overview";
  const query = useVideo(jobId);
  const cancel = useCancelVideo();
  const toast = useToast();
  const { download, pending: downloading } = useDownload();

  if (query.isLoading)
    return (
      <div className="flex justify-center py-24">
        <Spinner />
      </div>
    );
  if (query.isError || !query.data)
    return (
      <EmptyState
        title="Job introuvable"
        children={
          query.error instanceof ApiError && query.error.status === 401
            ? "Authentification requise — ajoute ta clé dans Réglages."
            : "Ce job n'existe pas ou a été purgé."
        }
      />
    );

  const job = query.data;
  const active = isActive(job.status);
  const failed = isFailed(job.status);
  const completed = job.status === "completed";

  function onCancel() {
    cancel.mutate(job.job_id, {
      onSuccess: () => toast.info("Annulation demandée."),
      onError: (e) => toast.error(e instanceof ApiError ? e.message : "Annulation impossible."),
    });
  }

  const tabs: { id: Tab; label: string; show: boolean }[] = [
    { id: "overview", label: "Aperçu", show: true },
    { id: "report", label: "Rapport", show: Boolean(job.report_url) },
    { id: "artifacts", label: "Artefacts", show: true },
  ];

  return (
    <div className="animate-fade-up">
      <Link to="/" className="mb-5 inline-flex items-center gap-1.5 text-sm text-muted transition-colors hover:text-ink">
        <ArrowLeft className="size-4" /> Tableau de bord
      </Link>

      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-2">
          <div className="flex items-center gap-3">
            <h1 className="font-mono text-xl font-semibold tracking-tight text-ink">{shortId(job.job_id)}</h1>
            <StatusPill status={job.status} />
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {job.language && <Chip>{languageName(job.language)}</Chip>}
            {job.production_mode && <Chip>{job.production_mode}</Chip>}
            {job.render_engine && <Chip>{job.render_engine}</Chip>}
            {job.quality_profile && <Chip>{job.quality_profile}</Chip>}
            {job.batch_id && (
              <Link to={`/batches/${job.batch_id}`}>
                <Chip className="bg-brand-50 text-brand-700 transition-colors hover:bg-brand-100">
                  <Layers className="size-3" /> vue batch
                </Chip>
              </Link>
            )}
            {typeof job.attempt_number === "number" && job.attempt_number > 0 && (
              <Chip className="bg-amber-50 text-amber">
                <Wrench className="size-3" /> Réparation {job.attempt_number}/{Math.max(1, (job.max_attempts ?? 1) - 1)}
              </Chip>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {completed && (
            <Button
              variant="primary"
              icon={<Download className="size-4" />}
              loading={downloading}
              onClick={() => download(api.downloadPath(job.job_id), `${shortId(job.job_id)}-${job.language ?? "video"}.mp4`)}
            >
              Télécharger
            </Button>
          )}
          {active && (
            <Button variant="danger" icon={<X className="size-4" />} loading={cancel.isPending} onClick={onCancel}>
              Annuler
            </Button>
          )}
        </div>
      </div>

      {/* Hero adapts to lifecycle state. */}
      {completed ? (
        <VideoPlayer jobId={job.job_id} />
      ) : failed ? (
        <Card className="border-danger/30 bg-danger-50/40 px-6 py-6">
          <div className="mb-5 flex items-center gap-2 text-danger">
            <AlertTriangle className="size-5" />
            <span className="font-display text-lg font-medium">La génération a échoué</span>
          </div>
          {job.error_message && (
            <p className="mb-6 rounded-lg bg-surface px-4 py-3 font-mono text-[13px] text-danger">{job.error_message}</p>
          )}
          <StageRailFull status={job.status} />
          <p className="mt-5 text-sm text-muted">
            Inspecte les{" "}
            <button onClick={() => setParams({ tab: "artifacts" })} className="font-medium text-brand-700 hover:underline">
              logs de rendu
            </button>{" "}
            pour le détail.
          </p>
        </Card>
      ) : job.status === "cancelled" ? (
        <Card className="flex items-center gap-3 px-6 py-8 text-muted">
          <Ban className="size-5" /> Job annulé.
        </Card>
      ) : (
        <Card className="px-6 py-7">
          <div className="mb-6 flex items-end justify-between gap-4">
            <div>
              <p className="font-mono text-xs tracking-wide text-faint uppercase">en cours</p>
              <p className="mt-1 font-display text-2xl font-medium text-ink">{prettyStep(job.current_step)}</p>
            </div>
            <div className="text-right">
              <p className="font-display text-4xl font-semibold tabular-nums text-brand">{job.progress}%</p>
            </div>
          </div>
          <StageRailFull status={job.status} />
          {job.last_repair_reason && (
            <div className="mt-5 flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2.5 text-xs text-amber">
              <Wrench className="mt-0.5 size-3.5 shrink-0" />
              <span className="line-clamp-2">
                <span className="font-medium">Réparation en cours :</span> {job.last_repair_reason}
              </span>
            </div>
          )}
          <p className="mt-6 flex items-center gap-2 text-xs text-muted">
            <span className="size-1.5 animate-rail-pulse rounded-full bg-brand" />
            Mise à jour automatique en direct
          </p>
        </Card>
      )}

      {/* Tabs */}
      <nav className="mt-8 mb-5 flex gap-1 border-b border-border">
        {tabs
          .filter((t) => t.show)
          .map((t) => (
            <button
              key={t.id}
              onClick={() => setParams(t.id === "overview" ? {} : { tab: t.id })}
              className={cn(
                "relative -mb-px px-4 py-2.5 text-sm font-medium transition-colors",
                tab === t.id ? "text-ink" : "text-muted hover:text-ink",
              )}
            >
              {t.label}
              {tab === t.id && <span className="absolute inset-x-3 -bottom-px h-0.5 rounded-full bg-brand" />}
            </button>
          ))}
      </nav>

      {tab === "report" && job.report_url ? (
        <ReportTab jobId={job.job_id} />
      ) : tab === "artifacts" ? (
        <ArtifactsTab jobId={job.job_id} />
      ) : (
        <OverviewTab job={query.data} />
      )}
    </div>
  );
}

function OverviewTab({ job }: { job: ReturnType<typeof useVideo>["data"] }) {
  if (!job) return null;
  const rows: { label: string; value: string }[] = [
    { label: "Identifiant", value: job.job_id },
    { label: "Statut", value: job.status },
    { label: "Étape", value: prettyStep(job.current_step) },
    { label: "Progression", value: `${job.progress}%` },
    { label: "Langue", value: languageName(job.language) },
    { label: "Mode", value: job.production_mode ?? "—" },
    { label: "Moteur", value: job.render_engine ?? "—" },
    { label: "Qualité", value: job.quality_profile ?? "—" },
    { label: "Batch", value: job.batch_id ? shortId(job.batch_id) : "—" },
  ];
  if (typeof job.attempt_number === "number" && job.attempt_number > 0) {
    const max = Math.max(1, (job.max_attempts ?? 1) - 1);
    rows.push({ label: "Tentative", value: `${job.attempt_number}/${max}` });
    if (job.last_repair_reason) {
      rows.push({ label: "Dernière raison", value: job.last_repair_reason });
    }
  }
  return (
    <Card className="divide-y divide-border">
      {rows.map((r) => (
        <div key={r.label} className="flex items-center justify-between gap-4 px-5 py-3">
          <span className="text-sm text-muted">{r.label}</span>
          <span className="truncate font-mono text-[13px] text-ink">{r.value}</span>
        </div>
      ))}
    </Card>
  );
}
