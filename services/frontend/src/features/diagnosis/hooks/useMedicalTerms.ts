/**
 * Loads the PrimeKG medical term set from the backend for symptom autocomplete.
 *
 * The backend exposes the term set at `/api/v1/metadata/medical-terms`.
 * Results are cached for the session since the term set never changes at runtime.
 */

import { useQuery } from "@tanstack/react-query";
import { QUERY_KEYS } from "@/lib/constants";
import { logger } from "@/lib/logger";

const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");
const API_KEY = import.meta.env.VITE_API_KEY ?? "";

async function fetchMedicalTerms(): Promise<string[]> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/metadata/medical-terms`, {
      headers: {
        Accept: "application/json",
        ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
      },
      cache: "force-cache",
    });
    if (!res.ok) {
      logger.warn("medical_terms.fetch_failed", { status: res.status });
      return [];
    }
    const data = (await res.json()) as string[];
    logger.info("medical_terms.loaded", { count: data.length });
    return data;
  } catch (err) {
    logger.warn("medical_terms.network_error", {
      error: (err as Error).message,
    });
    return [];
  }
}

export function useMedicalTerms() {
  return useQuery<string[]>({
    queryKey: QUERY_KEYS.medicalTerms,
    queryFn: fetchMedicalTerms,
    staleTime: Infinity,
    gcTime: Infinity,
    retry: 0,
  });
}
