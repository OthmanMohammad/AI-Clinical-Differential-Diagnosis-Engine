import * as React from "react";
import { Search, X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { GraphNode } from "@/types/api";

interface GraphSearchProps {
  nodes: GraphNode[];
  open: boolean;
  onClose: () => void;
  onSelect: (nodeId: string) => void;
  className?: string;
}

export function GraphSearch({ nodes, open, onClose, onSelect, className }: GraphSearchProps) {
  const [query, setQuery] = React.useState("");
  const [activeIndex, setActiveIndex] = React.useState(0);
  const inputRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 10);
    } else {
      setQuery("");
      setActiveIndex(0);
    }
  }, [open]);

  const matches = React.useMemo(() => {
    if (!query.trim()) return [];
    const q = query.toLowerCase();
    return nodes
      .filter((n) => n.name.toLowerCase().includes(q))
      .slice(0, 8);
  }, [nodes, query]);

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") onClose();
    else if (e.key === "Enter" && matches[activeIndex]) {
      onSelect(matches[activeIndex].id);
      onClose();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, matches.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.15 }}
          style={{
            backgroundColor: "hsl(var(--popover))",
            color: "hsl(var(--popover-foreground))",
          }}
          className={cn(
            "pointer-events-auto w-80 rounded-md border border-border shadow-2xl",
            className,
          )}
        >
          <div className="flex items-center gap-2 border-b border-border px-2">
            <Search className="h-3.5 w-3.5 text-muted-foreground" />
            <Input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKey}
              placeholder="Find a node…"
              className="h-9 flex-1 border-0 bg-transparent shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
            />
            <button
              type="button"
              onClick={onClose}
              className="text-muted-foreground hover:text-foreground"
              aria-label="Close"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          {matches.length > 0 && (
            <ul className="max-h-64 overflow-y-auto py-1">
              {matches.map((n, i) => (
                <li
                  key={n.id}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    onSelect(n.id);
                    onClose();
                  }}
                  onMouseEnter={() => setActiveIndex(i)}
                  className={cn(
                    "cursor-pointer px-3 py-1.5 text-sm",
                    i === activeIndex && "bg-accent text-accent-foreground",
                  )}
                >
                  <div className="flex items-center justify-between">
                    <span className="truncate">{n.name}</span>
                    <span className="ml-2 shrink-0 font-mono text-[10px] text-muted-foreground">
                      {n.type}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {query && matches.length === 0 && (
            <div className="px-3 py-6 text-center text-xs text-muted-foreground">
              No matches
            </div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
