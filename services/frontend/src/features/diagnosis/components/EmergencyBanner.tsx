import { AlertCircle, Phone } from "lucide-react";
import { motion } from "framer-motion";

import type { EmergencyResult } from "@/types/api";
import { capitalize } from "@/lib/utils";

interface EmergencyBannerProps {
  emergency: EmergencyResult;
}

export function EmergencyBanner({ emergency }: EmergencyBannerProps) {
  if (!emergency.triggered) return null;

  const patternLabel = emergency.pattern_name.replace(/_/g, " ");

  return (
    <motion.div
      initial={{ opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
      role="alert"
      aria-live="assertive"
      className="mesh-emergency relative overflow-hidden rounded-lg border-2 border-emergency bg-emergency/10 p-4"
    >
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-emergency/20">
          <AlertCircle className="h-5 w-5 text-emergency" />
        </div>
        <div className="flex-1 space-y-1.5">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-emergency">
              Potential medical emergency
            </h3>
            <span className="rounded bg-emergency/20 px-1.5 py-0.5 font-mono text-[10px] uppercase text-emergency">
              {patternLabel}
            </span>
          </div>
          <p className="text-sm text-foreground/90">{emergency.message}</p>
          <div className="flex items-center gap-2 pt-1">
            <Phone className="h-3.5 w-3.5 text-emergency" />
            <span className="text-xs font-medium text-emergency">
              Call emergency services immediately
            </span>
          </div>
        </div>
      </div>
      <div className="pointer-events-none absolute -right-16 -top-16 h-32 w-32 animate-pulse-glow rounded-full bg-emergency/20" />
    </motion.div>
  );
}
