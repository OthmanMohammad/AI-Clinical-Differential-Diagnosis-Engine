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
  const year = new Date().getFullYear();

  return (
    <footer
      className={cn(
        "border-border bg-card text-muted-foreground flex shrink-0 flex-col border-t px-4 py-2 text-[11px]",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-4">
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
      </div>
      <div className="mt-1 flex items-center justify-between">
        <span>&copy; {year} Mohammad Othman. MooseGlove is a portfolio demonstration project.</span>
        <div className="flex items-center gap-3">
          <a
            href="/disclaimer.html"
            className="hover:text-foreground underline underline-offset-2 transition-colors"
          >
            Medical Disclaimer
          </a>
          <a
            href="/privacy.html"
            className="hover:text-foreground underline underline-offset-2 transition-colors"
          >
            Privacy Policy
          </a>
        </div>
      </div>
    </footer>
  );
}
