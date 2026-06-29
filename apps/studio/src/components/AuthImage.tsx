import { useEffect, useState } from "react";
import { ImageOff } from "lucide-react";
import { api } from "../api/client";
import { cn } from "../lib/cn";

// Artifact images (snapshots) live behind the API key, so they can't be loaded
// with a plain <img src>. Fetch the bytes, then point at an object URL.
export function AuthImage({ path, alt, className }: { path: string; alt: string; className?: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    let made: string | null = null;
    setUrl(null);
    setFailed(false);
    api
      .fetchBlobUrl(path)
      .then((u) => {
        if (!active) {
          URL.revokeObjectURL(u);
          return;
        }
        made = u;
        setUrl(u);
      })
      .catch(() => setFailed(true));
    return () => {
      active = false;
      if (made) URL.revokeObjectURL(made);
    };
  }, [path]);

  if (failed)
    return (
      <div className={cn("flex items-center justify-center bg-surface-2 text-faint", className)}>
        <ImageOff className="size-5" />
      </div>
    );
  if (!url) return <div className={cn("animate-rail-pulse bg-surface-2", className)} />;
  return <img src={url} alt={alt} className={className} loading="lazy" />;
}
