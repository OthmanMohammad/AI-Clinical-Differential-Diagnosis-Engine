/**
 * Global keyboard shortcut registration.
 *
 * Uses react-hotkeys-hook under the hood. Exposes a single hook that wires
 * up every application-level shortcut in one place for discoverability.
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

  // Command palette
  useHotkeys(
    "mod+k",
    (e) => {
      e.preventDefault();
      toggleCommandPalette();
    },
    { enableOnFormTags: true },
  );

  // Help dialog
  useHotkeys("shift+/", (e) => {
    e.preventDefault();
    toggleHelp();
  });

  // Theme toggle
  useHotkeys(
    "mod+shift+t",
    (e) => {
      e.preventDefault();
      setTheme(resolvedTheme === "dark" ? "light" : "dark");
    },
    { enableOnFormTags: true },
  );

  // Fullscreen graph
  useHotkeys("f", (e) => {
    // Don't fire while typing in form fields
    const target = e.target as HTMLElement;
    if (target.tagName === "INPUT" || target.tagName === "TEXTAREA") return;
    e.preventDefault();
    toggleGraphFullscreen();
  });

  // Escape — close palette and exit fullscreen
  useHotkeys(
    "esc",
    () => {
      setCommandPaletteOpen(false);
      setGraphFullscreen(false);
    },
    { enableOnFormTags: true },
  );
}
