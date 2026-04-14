/**
 * Diagnosis mutation hook — wraps the API call and exposes loading, error,
 * and streaming-pipeline state to the UI.
 *
 * This hook uses the streaming endpoint when available and falls back to
 * the regular POST endpoint on any error, so the UI works in both modes.
 */

import * as React from "react";
import { ApiError, api, type StreamEvent } from "@/lib/api";
import type { DiagnosisResponse, PatientIntake } from "@/types/api";
import { logger } from "@/lib/logger";

export type PipelineStage =
  | "emergency_check"
  | "input_gates"
  | "vector_search"
  | "graph_traversal"
  | "context_assembly"
  | "llm_call"
  | "output_gates";

export interface StageStatus {
  name: PipelineStage;
  status: "pending" | "running" | "complete" | "error" | "skipped";
  elapsedMs?: number;
  detail?: string;
}

export const PIPELINE_STAGES: PipelineStage[] = [
  "emergency_check",
  "input_gates",
  "vector_search",
  "graph_traversal",
  "context_assembly",
  "llm_call",
  "output_gates",
];

const STAGE_LABELS: Record<PipelineStage, string> = {
  emergency_check: "Emergency check",
  input_gates: "Input validation",
  vector_search: "Vector search",
  graph_traversal: "Graph traversal",
  context_assembly: "Context assembly",
  llm_call: "LLM reasoning",
  output_gates: "Output validation",
};

export function getStageLabel(stage: PipelineStage): string {
  return STAGE_LABELS[stage];
}

interface UseDiagnosisState {
  isLoading: boolean;
  data: DiagnosisResponse | null;
  error: Error | null;
  stages: StageStatus[];
  run: (intake: PatientIntake) => Promise<void>;
  reset: () => void;
  cancel: () => void;
}

function initialStages(): StageStatus[] {
  return PIPELINE_STAGES.map((name) => ({ name, status: "pending" }));
}

export function useDiagnosis(): UseDiagnosisState {
  const [data, setData] = React.useState<DiagnosisResponse | null>(null);
  const [error, setError] = React.useState<Error | null>(null);
  const [isLoading, setIsLoading] = React.useState(false);
  const [stages, setStages] = React.useState<StageStatus[]>(() => initialStages());
  const abortRef = React.useRef<AbortController | null>(null);

  const reset = React.useCallback(() => {
    setData(null);
    setError(null);
    setStages(initialStages());
  }, []);

  const cancel = React.useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setIsLoading(false);
  }, []);

  const run = React.useCallback(
    async (intake: PatientIntake): Promise<void> => {
      cancel();
      reset();
      setIsLoading(true);
      setStages(initialStages());

      const startedAt = performance.now();
      logger.info("diagnosis.start", { symptoms: intake.symptoms });

      // Attempt streaming first
      const streamed = await tryStream(intake, setStages).catch(() => null);
      if (streamed) {
        setData(streamed);
        setIsLoading(false);
        logger.info("diagnosis.complete", {
          source: "stream",
          elapsed_ms: Math.round(performance.now() - startedAt),
          diagnoses: streamed.diagnoses.length,
        });
        return;
      }

      // Fallback to non-streaming
      try {
        const controller = new AbortController();
        abortRef.current = controller;
        // Mark all stages as running sequentially in the UI so the stepper
        // doesn't look frozen while the single POST is in flight.
        setStages((prev) =>
          prev.map((s, i) => ({
            ...s,
            status: i === 0 ? "running" : "pending",
          })),
        );
        const response = await api.diagnose(intake, controller.signal);
        setData(response);
        setStages(() =>
          PIPELINE_STAGES.map((name) => ({ name, status: "complete" })),
        );
        logger.info("diagnosis.complete", {
          source: "fallback",
          elapsed_ms: Math.round(performance.now() - startedAt),
          diagnoses: response.diagnoses.length,
        });
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        const e = err instanceof Error ? err : new Error(String(err));
        setError(e);
        setStages((prev) =>
          prev.map((s) =>
            s.status === "running" ? { ...s, status: "error" } : s,
          ),
        );
        logger.error("diagnosis.error", { error: e.message });
      } finally {
        setIsLoading(false);
        abortRef.current = null;
      }
    },
    [cancel, reset],
  );

  // Cancel on unmount
  React.useEffect(() => {
    return () => cancel();
  }, [cancel]);

  return { isLoading, data, error, stages, run, reset, cancel };
}

/**
 * Attempts a streaming diagnosis. Returns the final response or null if
 * streaming is unavailable (in which case the caller should fall back).
 */
async function tryStream(
  intake: PatientIntake,
  setStages: React.Dispatch<React.SetStateAction<StageStatus[]>>,
): Promise<DiagnosisResponse | null> {
  return new Promise<DiagnosisResponse | null>((resolve, reject) => {
    let final: DiagnosisResponse | null = null;
    let anyEvent = false;

    const controller = api.diagnoseStream(intake, {
      onEvent: (event: StreamEvent) => {
        anyEvent = true;
        if (event.type === "stage_start" && event.stage) {
          setStages((prev) =>
            prev.map((s) =>
              s.name === event.stage ? { ...s, status: "running" } : s,
            ),
          );
        } else if (event.type === "stage_end" && event.stage) {
          setStages((prev) =>
            prev.map((s) =>
              s.name === event.stage
                ? {
                    ...s,
                    status: "complete",
                    elapsedMs: event.elapsed_ms,
                    detail: typeof event.data === "string" ? event.data : undefined,
                  }
                : s,
            ),
          );
        } else if (event.type === "emergency") {
          setStages((prev) =>
            prev.map((s, i) =>
              i === 0 ? { ...s, status: "complete" } : { ...s, status: "skipped" },
            ),
          );
        } else if (event.type === "diagnosis_ready") {
          final = event.data as DiagnosisResponse;
        }
      },
      onDone: (response) => {
        resolve(response ?? final);
      },
      onError: (err) => {
        // If we never received any event, streaming isn't supported — return null
        // so the caller can fall back to the non-streaming endpoint.
        if (!anyEvent || (err instanceof ApiError && err.status === 404)) {
          resolve(null);
        } else {
          reject(err);
        }
      },
    });

    // Safety: if it takes too long, bail out
    const timeout = setTimeout(() => {
      controller.abort();
      resolve(null);
    }, 60_000);

    // Cleanup handler
    return () => clearTimeout(timeout);
  });
}
