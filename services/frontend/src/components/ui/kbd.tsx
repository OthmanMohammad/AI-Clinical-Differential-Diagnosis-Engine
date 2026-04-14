import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Keyboard shortcut label — styled to look like a physical key cap.
 */
export const Kbd = React.forwardRef<
  HTMLElement,
  React.HTMLAttributes<HTMLElement>
>(({ className, children, ...props }, ref) => (
  <kbd
    ref={ref}
    className={cn(
      "pointer-events-none inline-flex h-5 select-none items-center gap-1 rounded border border-border bg-muted/50 px-1.5 font-mono text-[10px] font-medium text-muted-foreground opacity-100",
      className,
    )}
    {...props}
  >
    {children}
  </kbd>
));
Kbd.displayName = "Kbd";
