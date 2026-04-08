/** Emergency banner — shown when emergency pattern triggers. */

import { motion } from "framer-motion";
import type { EmergencyResult } from "@/types/api";

interface EmergencyBannerProps {
  emergency: EmergencyResult;
}

export default function EmergencyBanner({ emergency }: EmergencyBannerProps) {
  if (!emergency.triggered) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: -20 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-red-900/80 border-2 border-red-500 rounded-lg p-4 mb-4"
    >
      <div className="flex items-center gap-3">
        <span className="text-2xl">!!!</span>
        <div>
          <h3 className="text-red-200 font-bold text-lg">
            POTENTIAL MEDICAL EMERGENCY DETECTED
          </h3>
          <p className="text-red-300 text-sm mt-1">{emergency.message}</p>
          <p className="text-red-400 text-xs mt-2">
            Pattern: {emergency.pattern_name.replace(/_/g, " ")}
          </p>
        </div>
      </div>
    </motion.div>
  );
}
