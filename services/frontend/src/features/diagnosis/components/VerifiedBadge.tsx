import { AlertTriangle, CheckCircle2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface VerifiedBadgeProps {
  verified: boolean;
}

export function VerifiedBadge({ verified }: VerifiedBadgeProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge
          variant={verified ? "success" : "warning"}
          className="h-5 gap-1 px-1.5 text-[10px]"
        >
          {verified ? (
            <CheckCircle2 className="h-2.5 w-2.5" />
          ) : (
            <AlertTriangle className="h-2.5 w-2.5" />
          )}
          {verified ? "Verified" : "Unverified"}
        </Badge>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs">
        {verified
          ? "This diagnosis was found in the knowledge graph as an exact match."
          : "The LLM returned this name, but it does not exactly match any disease in the knowledge graph. Verify manually before relying on it."}
      </TooltipContent>
    </Tooltip>
  );
}
