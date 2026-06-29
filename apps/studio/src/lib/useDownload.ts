import { useState } from "react";
import { api, ApiError } from "../api/client";
import { useToast } from "../components/Toast";

// Authenticated download: pull bytes with the X-API-Key header, then trigger a
// browser save from the resulting object URL. A plain <a href> can't carry the
// header, so it would 401 whenever auth is enabled.
export function useDownload() {
  const [pending, setPending] = useState(false);
  const toast = useToast();

  async function download(path: string, filename: string) {
    setPending(true);
    try {
      const url = await api.fetchBlobUrl(path);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Téléchargement impossible.");
    } finally {
      setPending(false);
    }
  }

  return { download, pending };
}
