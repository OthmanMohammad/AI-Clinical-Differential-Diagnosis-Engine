import { ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";

interface FooterProps {
  modelUsed?: string;
  promptVersion?: string;
  requestId?: string;
  className?: string;
}

const DISCLAIMER =
  "This is a clinical decision support tool, not a diagnostic device. It has not been validated by a physician. Do not use as the sole basis for any clinical decision.";

export function Footer({ modelUsed, promptVersion, requestId, className }: FooterProps) {
  return (
    <footer
      className={cn(
        "flex h-8 shrink-0 items-center justify-between gap-4 border-t border-border bg-card px-4 text-[11px] text-muted-foreground",
        className,
      )}
    >
      <div className="flex items-center gap-2">
        <ShieldAlert className="h-3 w-3 shrink-0 text-[hsl(var(--warning))]" />
        <span className="truncate">{DISCLAIMER}</span>
      </div>
      <div className="flex shrink-0 items-center gap-3 font-mono">
        {modelUsed && (
          <span>
            model <span className="text-foreground/70">{modelUsed}</span>
          </span>
        )}
        {promptVersion && (
          <span>
            prompt <span className="text-foreground/70">v{promptVersion}</span>
          </span>
        )}
        {requestId && (
          <span>
            req <span className="text-foreground/70">{requestId.slice(0, 8)}</span>
          </span>
        )}
      </div>
    </footer>
  );
}
