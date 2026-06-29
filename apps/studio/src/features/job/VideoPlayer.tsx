import { useEffect, useState } from "react";
import { AlertCircle } from "lucide-react";
import { api, ApiError } from "../../api/client";
import { Spinner } from "../../components/ui";

// Streams the MP4 via an authenticated fetch into an object URL, because a
// native <video src> can't send X-API-Key. Fine for short explainer clips.
export function VideoPlayer({ jobId }: { jobId: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let revoked = false;
    let objectUrl: string | null = null;
    setUrl(null);
    setError(null);
    api
      .fetchBlobUrl(api.downloadPath(jobId))
      .then((u) => {
        if (revoked) {
          URL.revokeObjectURL(u);
          return;
        }
        objectUrl = u;
        setUrl(u);
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Lecture impossible.");
      });
    return () => {
      revoked = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [jobId]);

  return (
    <div className="relative aspect-video w-full overflow-hidden rounded-[var(--radius-card)] border border-border bg-ink">
      {url ? (
        <video src={url} controls autoPlay className="size-full" />
      ) : error ? (
        <div className="flex size-full flex-col items-center justify-center gap-2 text-center text-sm text-white/80">
          <AlertCircle className="size-6 text-danger" />
          {error}
        </div>
      ) : (
        <div className="flex size-full flex-col items-center justify-center gap-3 text-sm text-white/60">
          <Spinner className="text-white/60" />
          Chargement de la vidéo…
        </div>
      )}
    </div>
  );
}
