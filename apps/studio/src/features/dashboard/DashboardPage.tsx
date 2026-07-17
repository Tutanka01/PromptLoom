import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Film, Plus, KeyRound, RefreshCw, Trash2 } from "lucide-react";
import { useVideoList, usePurgeVideo } from "../../api/queries";
import { ApiError } from "../../api/client";
import type { VideoStatus } from "../../api/types";
import { isActive, isFailed } from "../../lib/steps";
import { Button, Card, EmptyState, Spinner } from "../../components/ui";
import { cn } from "../../lib/cn";
import { JobRow } from "./JobRow";
import { useToast } from "../../components/Toast";

type Filter = "all" | "active" | "done" | "failed";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "Tous" },
  { id: "active", label: "En cours" },
  { id: "done", label: "Terminés" },
  { id: "failed", label: "Échoués" },
];

function matches(job: VideoStatus, f: Filter): boolean {
  if (f === "all") return true;
  if (f === "active") return isActive(job.status);
  if (f === "done") return job.status === "completed";
  return isFailed(job.status) || job.status === "cancelled";
}

export function DashboardPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const purge = usePurgeVideo();
  const [filter, setFilter] = useState<Filter>("all");
  const [limit, setLimit] = useState(50);
  const query = useVideoList({ limit });

  const jobs = query.data?.jobs ?? [];
  const counts = useMemo(
    () => ({
      all: jobs.length,
      active: jobs.filter((j) => isActive(j.status)).length,
      done: jobs.filter((j) => j.status === "completed").length,
      failed: jobs.filter((j) => isFailed(j.status) || j.status === "cancelled").length,
    }),
    [jobs],
  );
  const visible = jobs.filter((j) => matches(j, filter));
  const liveCount = counts.active;
  const failedJobs = useMemo(
    () => jobs.filter((j) => isFailed(j.status) || j.status === "cancelled"),
    [jobs],
  );

  async function handleBulkPurgeFailed() {
    if (failedJobs.length === 0) return;
    if (
      !window.confirm(
        `Supprimer définitivement ${failedJobs.length} job(s) échoué(s) ou annulé(s) ?\n\nLes vidéos, artefacts et logs seront effacés.`,
      )
    )
      return;
    // Fire-and-collect. Fail one → keep going; report the count.
    const results = await Promise.allSettled(
      failedJobs.map((j) => purge.mutateAsync(j.job_id)),
    );
    const ok = results.filter((r) => r.status === "fulfilled").length;
    const ko = results.length - ok;
    if (ko === 0) toast.info(`${ok} job(s) supprimé(s).`);
    else if (ok === 0) toast.error(`Aucun job supprimé — ${ko} erreur(s).`);
    else toast.info(`${ok} supprimé(s), ${ko} en erreur.`);
    void query.refetch();
  }

  return (
    <div className="animate-fade-up">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Tableau de bord</h1>
          <p className="mt-1 flex items-center gap-2 text-sm text-muted">
            {jobs.length > 0 ? `${jobs.length} jobs` : "Aucun job pour l'instant"}
            {liveCount > 0 && (
              <span className="inline-flex items-center gap-1.5 text-brand-700">
                <RefreshCw className="size-3.5 animate-spin-slow" />
                {liveCount} en direct
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {filter === "failed" && failedJobs.length > 0 && (
            <button
              onClick={handleBulkPurgeFailed}
              disabled={purge.isPending}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-danger/30 bg-danger-50 px-2.5 text-[13px] font-medium text-danger transition-colors hover:bg-danger hover:text-white disabled:opacity-50"
              title="Supprimer les jobs échoués et annulés visibles"
            >
              <Trash2 className="size-4" /> Purger les échoués ({failedJobs.length})
            </button>
          )}
          <div className="flex gap-1 rounded-lg border border-border bg-inset p-1">
            {FILTERS.map((f) => (
              <button
                key={f.id}
                onClick={() => setFilter(f.id)}
                className={cn(
                  "rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors",
                  filter === f.id ? "bg-surface text-ink shadow-sm ring-1 ring-border" : "text-muted hover:text-ink",
                )}
              >
                {f.label}
                <span className="ml-1.5 font-mono text-[11px] text-faint">{counts[f.id]}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {query.isLoading ? (
        <ListSkeleton />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : jobs.length === 0 ? (
        <EmptyState
          icon={<Film className="size-10" strokeWidth={1.5} />}
          title="Pas encore de vidéo"
          children={
            <div className="flex flex-col items-center gap-4">
              <p>Lance ta première génération pour la voir apparaître ici, progression en direct.</p>
              <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => navigate("/create")}>
                Nouvelle vidéo
              </Button>
            </div>
          }
        />
      ) : visible.length === 0 ? (
        <Card className="px-6 py-12 text-center text-sm text-muted">
          Aucun job dans cette catégorie.
        </Card>
      ) : (
        <div className="flex flex-col gap-3">
          {visible.map((job) => (
            <JobRow key={job.job_id} job={job} />
          ))}
        </div>
      )}

      {query.data && jobs.length >= limit && (
        <div className="mt-6 flex justify-center">
          <Button variant="default" onClick={() => setLimit((l) => l + 50)} loading={query.isFetching}>
            Charger plus
          </Button>
        </div>
      )}
    </div>
  );
}

function ListSkeleton() {
  return (
    <div className="flex flex-col gap-3">
      {[0, 1, 2].map((i) => (
        <div key={i} className="rounded-[var(--radius-card)] border border-border bg-surface p-5">
          <div className="flex items-center justify-between">
            <div className="h-4 w-32 rounded bg-surface-2" />
            <div className="h-6 w-20 rounded-full bg-surface-2" />
          </div>
          <div className="mt-4 h-1.5 w-full rounded-full bg-surface-2" />
          <div className="mt-3 h-3 w-40 rounded bg-surface-2" />
        </div>
      ))}
    </div>
  );
}

function ErrorState({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const unauthorized = error instanceof ApiError && error.status === 401;
  return (
    <EmptyState
      icon={unauthorized ? <KeyRound className="size-10" strokeWidth={1.5} /> : <Spinner />}
      title={unauthorized ? "Authentification requise" : "Impossible de charger les jobs"}
      children={
        <div className="flex flex-col items-center gap-4">
          <p>
            {unauthorized
              ? "L'API exige une clé. Ajoute-la dans Réglages (en haut à droite)."
              : error instanceof ApiError
                ? error.message
                : "Vérifie que l'API répond."}
          </p>
          <Button variant="default" onClick={onRetry}>
            Réessayer
          </Button>
        </div>
      }
    />
  );
}
