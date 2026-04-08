/** API client for PathoDX backend. */

import type { PatientIntake, DiagnosisResponse } from "@/types/api";

const API_BASE = import.meta.env.VITE_API_URL ?? "";
const API_KEY = import.meta.env.VITE_API_KEY ?? "";

class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": API_KEY,
      ...options?.headers,
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(
      res.status,
      typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail),
    );
  }

  return res.json() as Promise<T>;
}

export async function submitDiagnosis(
  intake: PatientIntake,
): Promise<DiagnosisResponse> {
  return request<DiagnosisResponse>("/api/v1/diagnose", {
    method: "POST",
    body: JSON.stringify(intake),
  });
}

export async function checkHealth(): Promise<{ status: string }> {
  return request<{ status: string }>("/health");
}

export { ApiError };
