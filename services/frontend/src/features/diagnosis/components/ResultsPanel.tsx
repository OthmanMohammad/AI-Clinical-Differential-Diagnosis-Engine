/**
 * Results panel — the center of the workspace.
 *
 * Renders one of five states:
 *   1. Empty (no query submitted yet)
 *   2. Loading (pipeline stepper streaming)
 *   3. Error (ApiError or network failure)
 *   4. Emergency (short-circuit branch)
 *   5. Success (ranked diagnoses)
 */

import * as React from "react";
import { AlertOctagon, Brain, Sparkles, RefreshCcw } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { DiagnosisCard } from "@/features/diagnosis/components/DiagnosisCard";
import { EmergencyBanner } from "@/features/diagnosis/components/EmergencyBanner";
import { PipelineStepper } from "@/features/diagnosis/components/PipelineStepper";
import { DiagnosisSkeleton } from "@/features/diagnosis/components/DiagnosisSkeleton";
import type { StageStatus } from "@/features/diagnosis/hooks/useDiagnosis";
import type { DiagnosisResponse } from "@/types/api";

interface ResultsPanelProps {
  isLoading: boolean;
  data: DiagnosisResponse | null;
  error: Error | null;
  stages: StageStatus[];
  onRetry?: () => void;
  onHighlightDiagnosis?: (diseaseName: string | null) => void;
  highlightedDiagnosis?: string | null;
}

export function ResultsPanel({
  isLoading,
  data,
  error,
  stages,
  onRetry,
  onHighlightDiagnosis,
  highlightedDiagnosis,
}: ResultsPanelProps) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-h3 font-semibold tracking-tight">
            Differential diagnosis
          </h2>
          <p className="text-xs text-muted-foreground">
            Ranked by model confidence
          </p>
        </div>
        {data && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Badge variant="outline" className="gap-1 font-mono text-[10px]">
                <Sparkles className="h-2.5 w-2.5" />
                {data.diagnoses.length} diagnoses
              </Badge>
            </TooltipTrigger>
            <TooltipContent side="bottom">
              Verified against knowledge graph
            </TooltipContent>
          </Tooltip>
        )}
      </div>

      {/* Content */}
      <ScrollArea className="-mx-4 flex-1 px-4">
        <div className="space-y-3 pb-4">
          <AnimatePresence mode="wait">
            {error && (
              <ErrorState
                key="error"
                message={error.message}
                onRetry={onRetry}
              />
            )}

            {!error && isLoading && (
              <motion.div
                key="loading"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="space-y-3"
              >
                <PipelineStepper stages={stages} />
                <DiagnosisSkeleton />
              </motion.div>
            )}

            {!error && !isLoading && !data && (
              <EmptyState key="empty" />
            )}

            {!error && !isLoading && data && (
              <motion.div
                key="results"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="space-y-3"
              >
                <EmergencyBanner emergency={data.emergency} />

                {data.low_confidence && (
                  <WarningRow
                    tone="warning"
                    title="Low confidence"
                    body="All diagnoses scored below the threshold. Consider collecting additional clinical data."
                  />
                )}
                {data.low_context && (
                  <WarningRow
                    tone="info"
                    title="Limited graph context"
                    body="Fewer medical entities matched the input. Results may be incomplete."
                  />
                )}
                {data.treatment_advice_stripped && (
                  <WarningRow
                    tone="info"
                    title="Treatment advice removed"
                    body="Treatment language was detected and filtered from the output."
                  />
                )}

                {data.diagnoses.length > 0 ? (
                  <div className="space-y-3">
                    {data.diagnoses.map((d, i) => (
                      <DiagnosisCard
                        key={`${d.disease_name}-${i}`}
                        diagnosis={d}
                        rank={i + 1}
                        delay={i * 0.08}
                        onHighlight={onHighlightDiagnosis}
                        isHighlighted={
                          highlightedDiagnosis === d.disease_name
                        }
                      />
                    ))}
                  </div>
                ) : (
                  !data.emergency.triggered && (
                    <p className="py-8 text-center text-sm text-muted-foreground">
                      No diagnoses could be generated.
                    </p>
                  )
                )}

                {data.reasoning_summary && (
                  <ReasoningSummary text={data.reasoning_summary} />
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </ScrollArea>
    </div>
  );
}

function EmptyState() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      className="flex h-64 flex-col items-center justify-center text-center"
    >
      <div className="relative mb-4">
        <div className="absolute inset-0 animate-pulse-glow rounded-full" />
        <div className="relative flex h-14 w-14 items-center justify-center rounded-full border border-border bg-card">
          <Brain className="h-6 w-6 text-muted-foreground" />
        </div>
      </div>
      <h3 className="text-sm font-medium text-foreground">
        Ready to analyze
      </h3>
      <p className="mt-1 max-w-xs text-xs text-muted-foreground">
        Enter patient symptoms and press{" "}
        <span className="font-mono text-foreground">Ctrl + ↵</span> to generate
        a ranked differential diagnosis with graph-backed reasoning.
      </p>
    </motion.div>
  );
}

function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      className="rounded-lg border border-destructive/40 bg-destructive/5 p-4"
    >
      <div className="flex items-start gap-3">
        <AlertOctagon className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-destructive">
            Diagnosis failed
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">{message}</p>
          {onRetry && (
            <Button
              variant="outline"
              size="sm"
              className="mt-3 gap-1.5"
              onClick={onRetry}
            >
              <RefreshCcw className="h-3 w-3" />
              Retry
            </Button>
          )}
        </div>
      </div>
    </motion.div>
  );
}

interface WarningRowProps {
  tone: "warning" | "info";
  title: string;
  body: string;
}

function WarningRow({ tone, title, body }: WarningRowProps) {
  const toneClass =
    tone === "warning"
      ? "border-[hsl(var(--warning))]/40 bg-[hsl(var(--warning))]/5 text-[hsl(var(--warning))]"
      : "border-[hsl(var(--info))]/40 bg-[hsl(var(--info))]/5 text-[hsl(var(--info))]";

  return (
    <motion.div
      initial={{ opacity: 0, x: -4 }}
      animate={{ opacity: 1, x: 0 }}
      className={`rounded-md border px-3 py-2 text-xs ${toneClass}`}
    >
      <div className="font-semibold">{title}</div>
      <div className="mt-0.5 opacity-90">{body}</div>
    </motion.div>
  );
}

function ReasoningSummary({ text }: { text: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.3 }}
      className="rounded-lg border border-border bg-muted/20 p-4"
    >
      <h4 className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Reasoning summary
      </h4>
      <p className="text-xs leading-relaxed text-foreground/90">{text}</p>
    </motion.div>
  );
}
