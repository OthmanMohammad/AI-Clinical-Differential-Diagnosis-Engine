/**
 * Global keyboard shortcuts.
 *
 * Curated list — only shortcuts that actually work cross-browser and
 * provide real value. Avoid sequences that conflict with browser
 * defaults (Ctrl+/, Ctrl+F outside the graph, etc.).
 */

import { useHotkeys } from "react-hotkeys-hook";
import { useTheme } from "@/hooks/useTheme";
import { useWorkspaceStore } from "@/features/diagnosis/store/workspace";

export function useGlobalShortcuts() {
  const toggleCommandPalette = useWorkspaceStore((s) => s.toggleCommandPalette);
  const setCommandPaletteOpen = useWorkspaceStore((s) => s.setCommandPaletteOpen);
  const toggleGraphFullscreen = useWorkspaceStore((s) => s.toggleGraphFullscreen);
  const setGraphFullscreen = useWorkspaceStore((s) => s.setGraphFullscreen);
  const toggleHelp = useWorkspaceStore((s) => s.toggleHelp);
  const { setTheme, resolvedTheme } = useTheme();

  // Cmd/Ctrl+K — Command palette
  useHotkeys(
    "mod+k",
    (e) => {
      e.preventDefault();
      toggleCommandPalette();
    },
    { enableOnFormTags: true },
  );

  // ? — Help dialog
  useHotkeys("shift+/", (e) => {
    const target = e.target as HTMLElement;
    if (target.tagName === "INPUT" || target.tagName === "TEXTAREA") return;
    e.preventDefault();
    toggleHelp();
  });

  // Cmd/Ctrl+Shift+L — Toggle theme (avoids browser conflict with Ctrl+Shift+T)
  useHotkeys(
    "mod+shift+l",
    (e) => {
      e.preventDefault();
      setTheme(resolvedTheme === "dark" ? "light" : "dark");
    },
    { enableOnFormTags: true },
  );

  // F — Fullscreen graph (only when not typing)
  useHotkeys("f", (e) => {
    const target = e.target as HTMLElement;
    if (target.tagName === "INPUT" || target.tagName === "TEXTAREA") return;
    e.preventDefault();
    toggleGraphFullscreen();
  });

  // Escape — close palette / exit fullscreen
  useHotkeys(
    "esc",
    () => {
      setCommandPaletteOpen(false);
      setGraphFullscreen(false);
    },
    { enableOnFormTags: true },
  );
}
