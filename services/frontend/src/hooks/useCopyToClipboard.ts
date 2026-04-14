/**
 * Copy-to-clipboard hook with a transient "copied" state.
 */

import * as React from "react";
import { logger } from "@/lib/logger";

interface UseCopyReturn {
  copy: (text: string) => Promise<boolean>;
  copied: boolean;
}

export function useCopyToClipboard(resetMs = 2000): UseCopyReturn {
  const [copied, setCopied] = React.useState(false);
  const timeoutRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  const copy = React.useCallback(
    async (text: string): Promise<boolean> => {
      if (!navigator?.clipboard) {
        logger.warn("clipboard.unsupported");
        return false;
      }
      try {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        if (timeoutRef.current) clearTimeout(timeoutRef.current);
        timeoutRef.current = setTimeout(() => setCopied(false), resetMs);
        return true;
      } catch (err) {
        logger.warn("clipboard.write_failed", { error: (err as Error).message });
        return false;
      }
    },
    [resetMs],
  );

  React.useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  return { copy, copied };
}
