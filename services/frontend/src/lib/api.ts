/**
 * HTTP client for the PathoDX backend.
 *
 * All requests go through this module so we have a single place to add
 * authentication, tracing, and error normalization.
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
 * Normalized API error — carries the HTTP status and a structured detail.
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
    logger.error("api.network_error", { url, error: (err as Error).message });
    throw new ApiError(0, "Network request failed");
  }

  const elapsed = Math.round(performance.now() - started);
  const requestId = response.headers.get("x-request-id") ?? undefined;

  if (!response.ok) {
    let detail: unknown = response.statusText;
    try {
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

  // Caller may pass an empty-body endpoint; handle gracefully.
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

  /** Health check. */
  health(signal?: AbortSignal): Promise<{ status: string; service: string }> {
    return request<{ status: string; service: string }>("/health", { signal });
  },

  /**
   * Streaming diagnosis via Server-Sent Events.
   * Returns an AbortController so the caller can cancel.
   *
   * The stream emits JSON events with shape `{ type: string; data: unknown }`.
   */
  diagnoseStream(
    intake: PatientIntake,
    callbacks: StreamCallbacks,
  ): AbortController {
    const controller = new AbortController();
    void runDiagnoseStream(intake, callbacks, controller.signal);
    return controller;
  },
};

// ---------------------------------------------------------------------------
// SSE streaming implementation
// ---------------------------------------------------------------------------

export interface StreamEvent {
  type:
    | "stage_start"
    | "stage_end"
    | "emergency"
    | "diagnosis_ready"
    | "error"
    | "done";
  stage?: string;
  elapsed_ms?: number;
  data?: unknown;
  message?: string;
}

export interface StreamCallbacks {
  onEvent(event: StreamEvent): void;
  onDone(response: DiagnosisResponse): void;
  onError(error: ApiError | Error): void;
}

async function runDiagnoseStream(
  intake: PatientIntake,
  callbacks: StreamCallbacks,
  signal: AbortSignal,
): Promise<void> {
  const url = `${API_BASE}/api/v1/diagnose/stream`;

  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { ...DEFAULT_HEADERS, Accept: "text/event-stream" },
      body: JSON.stringify(intake),
      signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") return;
    callbacks.onError(new ApiError(0, "Network request failed"));
    return;
  }

  if (!response.ok) {
    let detail: unknown;
    try {
      detail = await response.json();
    } catch {
      detail = response.statusText;
    }
    callbacks.onError(new ApiError(response.status, detail));
    return;
  }

  const body = response.body;
  if (!body) {
    callbacks.onError(new ApiError(0, "Empty response body"));
    return;
  }

  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResponse: DiagnosisResponse | null = null;

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // SSE frames are separated by blank lines.
      let frameEnd: number;
      while ((frameEnd = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, frameEnd);
        buffer = buffer.slice(frameEnd + 2);

        const dataLine = frame
          .split("\n")
          .find((line) => line.startsWith("data:"));
        if (!dataLine) continue;

        const payload = dataLine.slice(5).trim();
        if (!payload) continue;

        try {
          const event = JSON.parse(payload) as StreamEvent;
          callbacks.onEvent(event);
          if (event.type === "diagnosis_ready") {
            finalResponse = event.data as DiagnosisResponse;
          }
          if (event.type === "error") {
            callbacks.onError(new ApiError(500, event.message ?? "Stream error"));
            return;
          }
        } catch (err) {
          logger.warn("stream.parse_error", {
            payload,
            error: (err as Error).message,
          });
        }
      }
    }
  } catch (err) {
    if ((err as Error).name === "AbortError") return;
    callbacks.onError(err as Error);
    return;
  } finally {
    reader.releaseLock();
  }

  if (finalResponse) {
    callbacks.onDone(finalResponse);
  }
}
