import { AlertCircle, Phone } from "lucide-react";
import { motion } from "framer-motion";

import type { EmergencyResult } from "@/types/api";

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
      className="mesh-emergency border-emergency bg-emergency/10 relative overflow-hidden rounded-lg border-2 p-4"
    >
      <div className="flex items-start gap-3">
        <div className="bg-emergency/20 flex h-9 w-9 shrink-0 items-center justify-center rounded-full">
          <AlertCircle className="text-emergency h-5 w-5" />
        </div>
        <div className="flex-1 space-y-1.5">
          <div className="flex items-center gap-2">
            <h3 className="text-emergency text-sm font-semibold uppercase tracking-wide">
              Potential medical emergency
            </h3>
            <span className="bg-emergency/20 text-emergency rounded px-1.5 py-0.5 font-mono text-[10px] uppercase">
              {patternLabel}
            </span>
          </div>
          <p className="text-foreground/90 text-sm">{emergency.message}</p>
          <div className="flex items-center gap-2 pt-1">
            <Phone className="text-emergency h-3.5 w-3.5" />
            <span className="text-emergency text-xs font-medium">
              Call emergency services immediately
            </span>
          </div>
        </div>
      </div>
      <div className="animate-pulse-glow bg-emergency/20 pointer-events-none absolute -right-16 -top-16 h-32 w-32 rounded-full" />
    </motion.div>
  );
}
