import * as React from "react";
import { ChevronRight, Copy, Check } from "lucide-react";
import { motion } from "framer-motion";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ConfidenceBar } from "@/features/diagnosis/components/ConfidenceBar";
import { VerifiedBadge } from "@/features/diagnosis/components/VerifiedBadge";
import { useCopyToClipboard } from "@/hooks/useCopyToClipboard";
import { cn } from "@/lib/utils";
import type { DiagnosisItem } from "@/types/api";

interface DiagnosisCardProps {
  diagnosis: DiagnosisItem;
  rank: number;
  onHighlight?: (diseaseName: string | null) => void;
  isHighlighted?: boolean;
  delay?: number;
}

export function DiagnosisCard({
  diagnosis,
  rank,
  onHighlight,
  isHighlighted,
  delay = 0,
}: DiagnosisCardProps) {
  const [expanded, setExpanded] = React.useState(rank === 1);

  return (
    <motion.div
      initial={{ opacity: 0, x: 12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.35, delay, ease: [0.16, 1, 0.3, 1] }}
      onMouseEnter={() => onHighlight?.(diagnosis.disease_name)}
      onMouseLeave={() => onHighlight?.(null)}
    >
      <Card
        className={cn(
          "group relative overflow-hidden transition-all",
          isHighlighted && "ring-2 ring-primary/40",
        )}
      >
        {rank === 1 && (
          <div
            aria-hidden
            className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/60 to-transparent"
          />
        )}
        <div className="p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="flex min-w-0 flex-1 items-start gap-3">
              <span
                aria-label={`Rank ${rank}`}
                className={cn(
                  "flex h-7 w-7 shrink-0 items-center justify-center rounded-md font-mono text-xs tabular-nums",
                  rank === 1
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground",
                )}
              >
                {rank}
              </span>
              <div className="min-w-0 flex-1">
                <h3 className="break-words text-sm font-semibold leading-snug text-foreground">
                  {diagnosis.disease_name}
                </h3>
                <div className="mt-1.5">
                  <ConfidenceBar value={diagnosis.confidence} animationDelay={delay} />
                </div>
              </div>
            </div>
            <VerifiedBadge verified={diagnosis.verified_in_graph} />
          </div>

          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="mt-3 flex items-center gap-1 text-[11px] font-medium text-muted-foreground transition-colors hover:text-foreground"
            aria-expanded={expanded}
          >
            <ChevronRight
              className={cn(
                "h-3 w-3 transition-transform",
                expanded && "rotate-90",
              )}
            />
            {diagnosis.supporting_evidence.length} evidence items
          </button>

          <motion.div
            initial={false}
            animate={{
              height: expanded ? "auto" : 0,
              opacity: expanded ? 1 : 0,
            }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden"
          >
            <ul className="mt-2 space-y-1.5 border-t border-border pt-2">
              {diagnosis.supporting_evidence.map((ev, i) => (
                <EvidenceRow key={i} text={ev} />
              ))}
            </ul>
            {diagnosis.graph_path.length > 0 && (
              <div className="mt-2 border-t border-border pt-2">
                <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Graph path
                </p>
                <div className="flex flex-wrap items-center gap-1 font-mono text-[11px]">
                  {diagnosis.graph_path.map((node, i) => (
                    <React.Fragment key={i}>
                      <span className="rounded-sm bg-muted/60 px-1.5 py-0.5 text-foreground/80">
                        {node}
                      </span>
                      {i < diagnosis.graph_path.length - 1 && (
                        <ChevronRight className="h-3 w-3 text-muted-foreground" />
                      )}
                    </React.Fragment>
                  ))}
                </div>
              </div>
            )}
          </motion.div>
        </div>
      </Card>
    </motion.div>
  );
}

function EvidenceRow({ text }: { text: string }) {
  const { copy, copied } = useCopyToClipboard();

  return (
    <li className="group/row flex items-start gap-2 rounded-sm px-1.5 py-1 text-[11px] text-muted-foreground hover:bg-muted/40">
      <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-primary/60" />
      <span className="flex-1 break-words font-mono leading-snug">{text}</span>
      <Button
        variant="ghost"
        size="icon-sm"
        className="h-5 w-5 opacity-0 transition-opacity group-hover/row:opacity-100"
        onClick={() => void copy(text)}
        aria-label="Copy evidence"
      >
        {copied ? (
          <Check className="h-3 w-3 text-[hsl(var(--success))]" />
        ) : (
          <Copy className="h-3 w-3" />
        )}
      </Button>
    </li>
  );
}
