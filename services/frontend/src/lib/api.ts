/**
 * HTTP client for the PathoDX backend.
 *
 * Single typed entry point. All requests are normalized to either a
 * successful JSON response or an `ApiError` with a usable detail string.
 */

import type { DiagnosisResponse, PatientIntake } from "@/types/api";
import { logger } from "@/lib/logger";

const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");
const API_KEY = import.meta.env.VITE_API_KEY ?? "";

const DEFAULT_HEADERS: Record<string, string> = {
  "Content-Type": "application/json",
  Accept: "application/json",
};

if (API_KEY) {
  DEFAULT_HEADERS["X-API-Key"] = API_KEY;
}

/**
 * Normalized API error — carries the HTTP status, structured detail, and
 * the upstream request ID for log correlation.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;
  readonly requestId: string | undefined;

  constructor(status: number, detail: unknown, requestId?: string) {
    super(ApiError.formatMessage(detail));
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.requestId = requestId;
  }

  private static formatMessage(detail: unknown): string {
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") {
      const obj = detail as Record<string, unknown>;
      if (typeof obj.detail === "string") return obj.detail;
      if (typeof obj.title === "string") return obj.title;
    }
    return "An unexpected API error occurred";
  }
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  signal?: AbortSignal;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const url = `${API_BASE}${path}`;
  const init: RequestInit = {
    method: options.method ?? "GET",
    headers: { ...DEFAULT_HEADERS, ...(options.headers as Record<string, string>) },
    signal: options.signal,
  };

  if (options.body !== undefined) {
    init.body = JSON.stringify(options.body);
  }

  const started = performance.now();
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch (err) {
    if ((err as Error).name === "AbortError") {
      throw err;
    }
    logger.error("api.network_error", { url, error: (err as Error).message });
    throw new ApiError(0, "Network request failed");
  }

  const elapsed = Math.round(performance.now() - started);
  const requestId = response.headers.get("x-request-id") ?? undefined;

  if (!response.ok) {
    let detail: unknown = response.statusText;
    try {
      // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment -- response.json() is inherently untyped
      const parsed = await response.json();
      detail = (parsed as { detail?: unknown }).detail ?? parsed;
    } catch {
      /* ignore parse errors */
    }
    logger.warn("api.error_response", {
      url,
      status: response.status,
      elapsed,
      requestId,
    });
    throw new ApiError(response.status, detail, requestId);
  }

  logger.debug("api.success", { url, status: response.status, elapsed, requestId });

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return {} as T;
  }
  return (await response.json()) as T;
}

// ---------------------------------------------------------------------------
// Typed endpoints
// ---------------------------------------------------------------------------

export const api = {
  /** Submit a patient intake and receive a full differential diagnosis. */
  diagnose(intake: PatientIntake, signal?: AbortSignal): Promise<DiagnosisResponse> {
    return request<DiagnosisResponse>("/api/v1/diagnose", {
      method: "POST",
      body: intake,
      signal,
    });
  },

  /** Health check (liveness). */
  health(signal?: AbortSignal): Promise<{ status: string; service: string }> {
    return request<{ status: string; service: string }>("/health", { signal });
  },
};
