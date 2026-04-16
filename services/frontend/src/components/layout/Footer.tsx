import { ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";

interface FooterProps {
  modelUsed?: string;
  promptVersion?: string;
  requestId?: string;
  className?: string;
}

export function Footer({ modelUsed, promptVersion, requestId, className }: FooterProps) {
  const year = new Date().getFullYear();

  return (
    <footer
      className={cn(
        "border-border bg-card text-muted-foreground shrink-0 border-t text-[10px]",
        className,
      )}
    >
      {/* Top row: disclaimer bar */}
      <div className="flex items-center gap-2 px-3 py-1.5 md:px-4">
        <ShieldAlert className="h-3 w-3 shrink-0 text-[hsl(var(--warning))]" />
        <span className="truncate">
          Clinical decision support tool. Not a diagnostic device. Not validated by a physician.
        </span>
        <div className="ml-auto hidden shrink-0 items-center gap-3 font-mono md:flex">
          {modelUsed && (
            <span>
              model <span className="text-foreground/60">{modelUsed}</span>
            </span>
          )}
          {promptVersion && (
            <span>
              prompt <span className="text-foreground/60">v{promptVersion}</span>
            </span>
          )}
          {requestId && (
            <span>
              req <span className="text-foreground/60">{requestId.slice(0, 8)}</span>
            </span>
          )}
        </div>
      </div>

      {/* Bottom row: copyright + legal links */}
      <div className="border-border flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-t px-3 py-1.5 md:px-4">
        <span className="text-muted-foreground/70">&copy; {year} Mohammad Othman</span>
        <nav className="flex items-center gap-3" aria-label="Legal">
          <a href="/disclaimer.html" className="hover:text-foreground transition-colors">
            Medical Disclaimer
          </a>
          <span className="text-border">|</span>
          <a href="/privacy.html" className="hover:text-foreground transition-colors">
            Privacy
          </a>
        </nav>
      </div>
    </footer>
  );
}
