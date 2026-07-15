// TanStack Query hooks. Live progress is plain polling (the API offers no
// stream), but the interval is data-driven: it backs off to nothing once a job
// is terminal, so a finished dashboard stops hitting the network.

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
import { isActive } from "../lib/steps";

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
  return useQuery({
    queryKey: ["video", jobId],
    queryFn: () => api.getVideo(jobId as string),
    enabled: Boolean(jobId),
    refetchInterval: (query) =>
      query.state.data && isActive(query.state.data.status) ? ACTIVE_POLL_MS : false,
  });
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
