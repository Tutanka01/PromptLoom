// TanStack Query hooks. Live progress used to be plain polling (the API had no
// stream); the API now exposes GET /v1/videos/{id}/events (SSE) as well, so
// `useVideo` opens an EventSource in parallel when the browser supports it and
// piggybacks its snapshots into the same query cache. Polling stays as a
// fallback: the query keeps its refetchInterval so a proxy that strips SSE
// (or an older API) still gets progress via GET.

import { useEffect } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";
import { api } from "./client";
import type {
  BatchStatusResponse,
  CapabilitiesResponse,
  HealthResponse,
  VideoCreateRequest,
  VideoCreateResponse,
  VideoListResponse,
  VideoStatus,
  VoicesResponse,
} from "./types";
import { isActive, isTerminal } from "../lib/steps";

const ACTIVE_POLL_MS = 2500;

export function useVideoList(
  filter: { status?: string; limit?: number; offset?: number },
): UseQueryResult<VideoListResponse> {
  return useQuery({
    queryKey: ["videos", filter],
    queryFn: () => api.listVideos(filter),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data?.jobs?.some((j) => isActive(j.status))) return ACTIVE_POLL_MS;
      return false;
    },
    placeholderData: (prev) => prev,
  });
}

export function useVideo(jobId: string | undefined): UseQueryResult<VideoStatus> {
  const query = useQuery({
    queryKey: ["video", jobId],
    queryFn: () => api.getVideo(jobId as string),
    enabled: Boolean(jobId),
    refetchInterval: (q) =>
      q.state.data && isActive(q.state.data.status) ? ACTIVE_POLL_MS : false,
  });
  useJobEventStream(jobId, query.data?.status);
  return query;
}


/**
 * Open a Server-Sent Events stream to `/v1/videos/{id}/events` and merge every
 * incoming snapshot into the TanStack query cache. Falls back to plain polling
 * (already active on `useVideo`) when the browser doesn't ship EventSource, the
 * endpoint returns 404 (older API), or the connection drops mid-stream.
 *
 * The hook returns nothing: it exists purely for its side effect on the shared
 * cache.
 */
function useJobEventStream(jobId: string | undefined, status: string | undefined): void {
  const client = useQueryClient();
  useEffect(() => {
    if (!jobId) return;
    if (status && isTerminal(status)) return; // no point subscribing to a done job
    if (typeof window === "undefined" || typeof EventSource === "undefined") return;

    const source = new EventSource(api.eventsPath(jobId), { withCredentials: false });
    let closed = false;

    const applySnapshot = (raw: string) => {
      try {
        const snapshot = JSON.parse(raw) as Partial<VideoStatus>;
        client.setQueryData<VideoStatus>(["video", jobId], (prev) => ({
          ...(prev ?? ({ job_id: jobId, status: "queued", progress: 0 } as VideoStatus)),
          ...snapshot,
        }));
      } catch (err) {
        console.warn("useJobEventStream: bad snapshot", err);
      }
    };

    const finish = () => {
      if (closed) return;
      closed = true;
      source.close();
    };

    source.addEventListener("snapshot", (event) => applySnapshot((event as MessageEvent).data));
    source.addEventListener("state", (event) => applySnapshot((event as MessageEvent).data));
    source.addEventListener("terminal", (event) => {
      applySnapshot((event as MessageEvent).data);
      finish();
    });
    source.onerror = () => {
      // The browser will attempt to reconnect automatically until we close.
      // If the endpoint responds 404 (older API) or 401 (auth) the connection
      // will keep re-erroring; give up quickly and let polling take over.
      if (source.readyState === EventSource.CLOSED) finish();
    };

    return () => {
      finish();
    };
  }, [jobId, status, client]);
}

export function useBatch(batchId: string | undefined): UseQueryResult<BatchStatusResponse> {
  return useQuery({
    queryKey: ["batch", batchId],
    queryFn: () => api.getBatch(batchId as string),
    enabled: Boolean(batchId),
    refetchInterval: (query) =>
      query.state.data && query.state.data.jobs.some((j) => isActive(j.status))
        ? ACTIVE_POLL_MS
        : false,
  });
}

export function useHealth(): UseQueryResult<HealthResponse> {
  return useQuery({
    queryKey: ["health"],
    queryFn: () => api.getHealth(),
    refetchInterval: 30000,
    retry: false,
  });
}

// The catalog is deployment-defined (engine + voice bank): cache it hard and
// swallow errors — an older API without /v1/voices simply hides the selector.
export function useVoices(): UseQueryResult<VoicesResponse> {
  return useQuery({
    queryKey: ["voices"],
    queryFn: () => api.getVoices(),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

// Deployment-defined and cheap: cache it hard and swallow errors — an older
// API without /v1/capabilities falls back to the permissive built-in defaults
// (see lib/capabilities.ts).
export function useCapabilities(): UseQueryResult<CapabilitiesResponse> {
  return useQuery({
    queryKey: ["capabilities"],
    queryFn: () => api.getCapabilities(),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

export function useCreateVideo() {
  const qc = useQueryClient();
  return useMutation<VideoCreateResponse, Error, VideoCreateRequest>({
    mutationFn: (body) => api.createVideo(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["videos"] });
    },
  });
}

export function useCancelVideo() {
  const qc = useQueryClient();
  return useMutation<VideoStatus, Error, string>({
    mutationFn: (jobId) => api.cancelVideo(jobId),
    onSuccess: (data) => {
      qc.setQueryData(["video", data.job_id], data);
      void qc.invalidateQueries({ queryKey: ["videos"] });
    },
  });
}
