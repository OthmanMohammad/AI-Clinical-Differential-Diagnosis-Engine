/**
 * Type-safe localStorage hook with SSR fallback and cross-tab sync.
 */

import * as React from "react";
import { logger } from "@/lib/logger";

export function useLocalStorage<T>(
  key: string,
  defaultValue: T,
): [T, (value: T | ((prev: T) => T)) => void] {
  const readValue = React.useCallback((): T => {
    if (typeof window === "undefined") return defaultValue;
    try {
      const item = window.localStorage.getItem(key);
      return item ? (JSON.parse(item) as T) : defaultValue;
    } catch (err) {
      logger.warn("localStorage.read_failed", {
        key,
        error: (err as Error).message,
      });
      return defaultValue;
    }
  }, [key, defaultValue]);

  const [stored, setStored] = React.useState<T>(readValue);

  const setValue = React.useCallback(
    (value: T | ((prev: T) => T)) => {
      try {
        setStored((prev) => {
          const next =
            value instanceof Function ? value(prev) : value;
          window.localStorage.setItem(key, JSON.stringify(next));
          return next;
        });
      } catch (err) {
        logger.warn("localStorage.write_failed", {
          key,
          error: (err as Error).message,
        });
      }
    },
    [key],
  );

  // Cross-tab sync
  React.useEffect(() => {
    const handler = (e: StorageEvent) => {
      if (e.key !== key || e.newValue === null) return;
      try {
        setStored(JSON.parse(e.newValue) as T);
      } catch {
        /* ignore bad JSON */
      }
    };
    window.addEventListener("storage", handler);
    return () => window.removeEventListener("storage", handler);
  }, [key]);

  return [stored, setValue];
}
