/**
 * Pipeline progress stepper — animates through the backend pipeline stages
 * while a diagnosis is in flight.
 */

import { AlertCircle, Check, Loader2 } from "lucide-react";
import { motion } from "framer-motion";

import {
  getStageLabel,
  type StageStatus,
} from "@/features/diagnosis/hooks/useDiagnosis";
import { formatDuration } from "@/lib/utils";
import { cn } from "@/lib/utils";

interface PipelineStepperProps {
  stages: StageStatus[];
}

export function PipelineStepper({ stages }: PipelineStepperProps) {
  return (
    <div className="rounded-lg border border-border bg-card/50 p-4">
      <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Pipeline
      </h3>
      <ol className="relative space-y-3">
        <span
          aria-hidden
          className="absolute left-[9px] top-2 h-[calc(100%-16px)] w-px bg-border"
        />
        {stages.map((stage, idx) => (
          <StepRow key={stage.name} stage={stage} index={idx} />
        ))}
      </ol>
    </div>
  );
}

interface StepRowProps {
  stage: StageStatus;
  index: number;
}

function StepRow({ stage, index }: StepRowProps) {
  const label = getStageLabel(stage.name);

  return (
    <li className="relative flex items-start gap-3 pl-0">
      <StepIcon status={stage.status} index={index} />
      <div className="min-w-0 flex-1 pt-[1px]">
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "text-xs font-medium transition-colors",
              stage.status === "running" && "text-foreground",
              stage.status === "complete" && "text-foreground/80",
              stage.status === "pending" && "text-muted-foreground",
              stage.status === "error" && "text-destructive",
            )}
          >
            {label}
          </span>
          {stage.elapsedMs != null && stage.status === "complete" && (
            <span className="font-mono text-[10px] text-muted-foreground/70">
              {formatDuration(stage.elapsedMs)}
            </span>
          )}
        </div>
      </div>
    </li>
  );
}

function StepIcon({
  status,
  index,
}: {
  status: StageStatus["status"];
  index: number;
}) {
  return (
    <motion.div
      initial={{ scale: 0.6, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ delay: index * 0.04, duration: 0.2 }}
      className={cn(
        "relative z-10 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border transition-colors",
        status === "pending" && "border-border bg-background text-muted-foreground",
        status === "running" && "border-primary bg-background text-primary",
        status === "complete" &&
          "border-[hsl(var(--success))] bg-[hsl(var(--success))]/15 text-[hsl(var(--success))]",
        status === "error" && "border-destructive bg-destructive/15 text-destructive",
      )}
    >
      {status === "running" && <Loader2 className="h-3 w-3 animate-spin" />}
      {status === "complete" && <Check className="h-3 w-3" strokeWidth={3} />}
      {status === "error" && <AlertCircle className="h-3 w-3" />}
      {status === "pending" && (
        <span className="h-1.5 w-1.5 rounded-full bg-current opacity-40" />
      )}
    </motion.div>
  );
}
