/**
 * Theme hook — reads/writes the theme to the ThemeProvider context.
 * The provider handles localStorage persistence and DOM class updates.
 */

import { useContext } from "react";
import { ThemeContext, type ThemeContextValue } from "@/app/ThemeContext";

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme must be used within ThemeProvider");
  }
  return ctx;
}
