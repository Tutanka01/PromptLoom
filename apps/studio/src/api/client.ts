// Thin fetch client. Same-origin: paths go through the Vite dev proxy or the
// nginx reverse proxy, both forwarding /v1 and /healthz to the video-api.

import { getSettings } from "../lib/settings";
import type {
  BatchStatusResponse,
  CapabilitiesResponse,
  HealthResponse,
  VideoCreateRequest,
  VideoCreateResponse,
  VideoListResponse,
  VideoReport,
  VideoStatus,
  VoicesResponse,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function authHeaders(extra?: HeadersInit): Headers {
  const headers = new Headers(extra);
  const { apiKey } = getSettings();
  if (apiKey) headers.set("X-API-Key", apiKey);
  return headers;
}

async function toError(res: Response): Promise<ApiError> {
  let detail = res.statusText;
  try {
    const body = await res.json();
    if (body && typeof body.detail === "string") detail = body.detail;
    else if (Array.isArray(body?.detail) && body.detail[0]?.msg) {
      detail = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    }
  } catch {
    // Non-JSON error body; keep the status text.
  }
  if (res.status === 401) detail = "Clé API invalide ou manquante.";
  return new ApiError(res.status, detail);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: authHeaders({
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    }),
  });
  if (!res.ok) throw await toError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  createVideo(body: VideoCreateRequest): Promise<VideoCreateResponse> {
    return request("/v1/videos", { method: "POST", body: JSON.stringify(body) });
  },

  listVideos(params: { status?: string; limit?: number; offset?: number } = {}): Promise<VideoListResponse> {
    const q = new URLSearchParams();
    if (params.status) q.set("status", params.status);
    q.set("limit", String(params.limit ?? 50));
    q.set("offset", String(params.offset ?? 0));
    return request(`/v1/videos?${q.toString()}`);
  },

  getVideo(jobId: string): Promise<VideoStatus> {
    return request(`/v1/videos/${jobId}`);
  },

  cancelVideo(jobId: string): Promise<VideoStatus> {
    return request(`/v1/videos/${jobId}`, { method: "DELETE" });
  },

  getBatch(batchId: string): Promise<BatchStatusResponse> {
    return request(`/v1/batches/${batchId}`);
  },

  getReport(jobId: string): Promise<VideoReport> {
    return request(`/v1/videos/${jobId}/report`);
  },

  getHealth(): Promise<HealthResponse> {
    return request("/healthz");
  },

  getVoices(): Promise<VoicesResponse> {
    return request("/v1/voices");
  },

  getCapabilities(): Promise<CapabilitiesResponse> {
    return request("/v1/capabilities");
  },

  // Native <video>/<a> can't carry the X-API-Key header, so pull bytes with the
  // header and hand back an object URL. Caller must revoke it.
  async fetchBlobUrl(path: string): Promise<string> {
    const res = await fetch(path, { headers: authHeaders() });
    if (!res.ok) throw await toError(res);
    return URL.createObjectURL(await res.blob());
  },

  downloadPath(jobId: string): string {
    return `/v1/videos/${jobId}/download`;
  },

  artifactPath(jobId: string, artifact: string): string {
    return `/v1/videos/${jobId}/artifacts/${artifact}`;
  },

  async fetchArtifactText(jobId: string, artifact: string): Promise<string> {
    const res = await fetch(api.artifactPath(jobId, artifact), { headers: authHeaders() });
    if (!res.ok) throw await toError(res);
    return res.text();
  },
};
