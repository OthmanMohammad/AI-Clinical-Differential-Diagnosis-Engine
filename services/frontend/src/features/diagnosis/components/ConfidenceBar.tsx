import { motion } from "framer-motion";

import { cn, formatConfidence } from "@/lib/utils";

interface ConfidenceBarProps {
  value: number;
  animationDelay?: number;
  className?: string;
}

export function ConfidenceBar({ value, animationDelay = 0, className }: ConfidenceBarProps) {
  const pct = Math.max(0, Math.min(1, value));
  const tone =
    pct >= 0.7
      ? "bg-[hsl(var(--success))]"
      : pct >= 0.4
        ? "bg-[hsl(var(--warning))]"
        : "bg-destructive";

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="bg-muted h-1.5 flex-1 overflow-hidden rounded-full">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct * 100}%` }}
          transition={{
            duration: 0.8,
            delay: animationDelay,
            ease: [0.16, 1, 0.3, 1],
          }}
          className={cn("h-full rounded-full", tone)}
        />
      </div>
      <span className="text-foreground w-9 text-right font-mono text-xs tabular-nums">
        {formatConfidence(value)}
      </span>
    </div>
  );
}
