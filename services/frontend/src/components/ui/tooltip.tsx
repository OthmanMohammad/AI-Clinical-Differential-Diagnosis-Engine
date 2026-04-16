import * as React from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";

import { cn } from "@/lib/utils";

const TooltipProvider = TooltipPrimitive.Provider;
const Tooltip = TooltipPrimitive.Root;
const TooltipTrigger = TooltipPrimitive.Trigger;

const TooltipContent = React.forwardRef<
  React.ElementRef<typeof TooltipPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Content>
>(({ className, sideOffset = 6, ...props }, ref) => (
  <TooltipPrimitive.Portal>
    <TooltipPrimitive.Content
      ref={ref}
      sideOffset={sideOffset}
      style={{
        backgroundColor: "hsl(var(--popover))",
        color: "hsl(var(--popover-foreground))",
      }}
      className={cn(
        "border-border z-50 overflow-hidden rounded-md border px-2 py-1 text-xs shadow-xl",
        "data-[state=delayed-open]:data-[side=top]:animate-slide-down",
        "data-[state=delayed-open]:data-[side=bottom]:animate-slide-up",
        "data-[state=delayed-open]:data-[side=left]:animate-slide-up",
        "data-[state=delayed-open]:data-[side=right]:animate-slide-up",
        className,
      )}
      {...props}
    />
  </TooltipPrimitive.Portal>
));
TooltipContent.displayName = TooltipPrimitive.Content.displayName;

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider };
