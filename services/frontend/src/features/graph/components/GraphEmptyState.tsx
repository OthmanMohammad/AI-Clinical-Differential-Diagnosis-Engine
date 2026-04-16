import { motion } from "framer-motion";
import { Network } from "lucide-react";

export function GraphEmptyState() {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="bg-background/40 flex h-full flex-col items-center justify-center"
    >
      <div className="relative">
        {/* Decorative nodes */}
        <svg width={160} height={120} viewBox="0 0 160 120" className="text-muted-foreground/20">
          <circle cx="20" cy="30" r="6" fill="currentColor" />
          <circle cx="80" cy="20" r="8" fill="currentColor" />
          <circle cx="140" cy="40" r="6" fill="currentColor" />
          <circle cx="40" cy="80" r="5" fill="currentColor" />
          <circle cx="100" cy="90" r="7" fill="currentColor" />
          <line x1="20" y1="30" x2="80" y2="20" stroke="currentColor" strokeWidth="1" />
          <line x1="80" y1="20" x2="140" y2="40" stroke="currentColor" strokeWidth="1" />
          <line x1="80" y1="20" x2="40" y2="80" stroke="currentColor" strokeWidth="1" />
          <line x1="80" y1="20" x2="100" y2="90" stroke="currentColor" strokeWidth="1" />
          <line x1="140" y1="40" x2="100" y2="90" stroke="currentColor" strokeWidth="1" />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <Network className="text-muted-foreground/60 h-6 w-6" />
        </div>
      </div>
      <h3 className="text-foreground mt-4 text-sm font-medium">Reasoning graph</h3>
      <p className="text-muted-foreground mt-1 max-w-xs text-center text-xs">
        The medical knowledge graph used to generate the differential will appear here after
        analysis.
      </p>
    </motion.div>
  );
}
