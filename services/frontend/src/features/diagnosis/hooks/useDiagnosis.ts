/**
 * Diagnosis mutation hook.
 *
 * Sends the intake to /api/v1/diagnose and exposes loading, error, and
 * stage progress to the UI. The pipeline stepper is driven by a small
 * simulator that advances through stages on a fixed schedule while the
 * request is in flight — this gives the user visible progress feedback
 * even though the backend doesn't push real-time updates.
 */

import * as React from "react";
import { ApiError, api } from "@/lib/api";
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
  status: "pending" | "running" | "complete" | "error";
  elapsedMs?: number;
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

/**
 * Approximate latency for each pipeline stage in milliseconds.
 * These are realistic averages from running the pipeline against PrimeKG
 * with Groq Llama 3.3 70B. They drive the UI progress simulation while
 * the request is in flight.
 */
const STAGE_DURATIONS_MS: Record<PipelineStage, number> = {
  emergency_check: 80,
  input_gates: 30,
  vector_search: 600,
  graph_traversal: 3500,
  context_assembly: 60,
  llm_call: 4500,
  output_gates: 200,
};

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
  const simulatorTimers = React.useRef<ReturnType<typeof setTimeout>[]>([]);

  const clearSimulatorTimers = React.useCallback(() => {
    for (const t of simulatorTimers.current) {
      clearTimeout(t);
    }
    simulatorTimers.current = [];
  }, []);

  const reset = React.useCallback(() => {
    clearSimulatorTimers();
    setData(null);
    setError(null);
    setStages(initialStages());
  }, [clearSimulatorTimers]);

  const cancel = React.useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    clearSimulatorTimers();
    setIsLoading(false);
  }, [clearSimulatorTimers]);

  /**
   * Schedule the stepper animation to advance through stages on a fixed
   * timeline. If the request finishes early, `markAllComplete` overrides
   * the simulation with the real timings.
   */
  const startStageSimulation = React.useCallback(() => {
    clearSimulatorTimers();
    setStages(initialStages());

    let elapsed = 0;
    PIPELINE_STAGES.forEach((stage, index) => {
      // Schedule "running" at the start of this stage's window
      const startAt = elapsed;
      simulatorTimers.current.push(
        setTimeout(() => {
          setStages((prev) =>
            prev.map((s, i) =>
              i === index ? { ...s, status: "running" } : s,
            ),
          );
        }, startAt),
      );

      // Schedule "complete" at the end of this stage's window
      const endAt = elapsed + STAGE_DURATIONS_MS[stage];
      simulatorTimers.current.push(
        setTimeout(() => {
          setStages((prev) =>
            prev.map((s, i) =>
              i === index
                ? { ...s, status: "complete", elapsedMs: STAGE_DURATIONS_MS[stage] }
                : s,
            ),
          );
        }, endAt),
      );

      elapsed = endAt;
    });
  }, [clearSimulatorTimers]);

  const markAllComplete = React.useCallback(() => {
    clearSimulatorTimers();
    setStages((prev) =>
      prev.map((s) => ({ ...s, status: "complete" as const })),
    );
  }, [clearSimulatorTimers]);

  const markCurrentStageError = React.useCallback(() => {
    clearSimulatorTimers();
    setStages((prev) => {
      // Find first non-complete stage and mark it as error
      const idx = prev.findIndex((s) => s.status !== "complete");
      if (idx === -1) return prev;
      return prev.map((s, i) =>
        i === idx ? { ...s, status: "error" as const } : s,
      );
    });
  }, [clearSimulatorTimers]);

  const run = React.useCallback(
    async (intake: PatientIntake): Promise<void> => {
      cancel();
      setData(null);
      setError(null);
      setIsLoading(true);

      // Kick off the stepper simulator
      startStageSimulation();

      const startedAt = performance.now();
      logger.info("diagnosis.start", { symptoms: intake.symptoms });

      try {
        const controller = new AbortController();
        abortRef.current = controller;

        const response = await api.diagnose(intake, controller.signal);

        markAllComplete();
        setData(response);
        logger.info("diagnosis.complete", {
          elapsed_ms: Math.round(performance.now() - startedAt),
          diagnoses: response.diagnoses.length,
          model: response.model_used,
        });
      } catch (err) {
        if ((err as Error).name === "AbortError") {
          clearSimulatorTimers();
          return;
        }
        const e = err instanceof Error ? err : new Error(String(err));
        markCurrentStageError();
        setError(e);
        logger.error("diagnosis.error", {
          error: e.message,
          status: e instanceof ApiError ? e.status : undefined,
        });
      } finally {
        setIsLoading(false);
        abortRef.current = null;
      }
    },
    [
      cancel,
      startStageSimulation,
      markAllComplete,
      markCurrentStageError,
      clearSimulatorTimers,
    ],
  );

  // Cleanup on unmount
  React.useEffect(() => {
    return () => {
      cancel();
    };
  }, [cancel]);

  return { isLoading, data, error, stages, run, reset, cancel };
}
