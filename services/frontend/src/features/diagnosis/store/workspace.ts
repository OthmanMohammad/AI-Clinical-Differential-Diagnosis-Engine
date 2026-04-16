/**
 * Workspace-level UI state — panel sizes, sidebar, fullscreen graph.
 * Kept separate from diagnosis intake data so layout changes don't
 * invalidate form state and vice versa.
 */

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { STORAGE_KEYS } from "@/lib/constants";

interface WorkspaceState {
  /** Panel sizes (percentages) — must sum to 100. */
  panelSizes: [number, number, number];
  /** Sidebar collapsed state. */
  sidebarCollapsed: boolean;
  /** Graph fullscreen mode. */
  graphFullscreen: boolean;
  /** Command palette open. */
  commandPaletteOpen: boolean;
  /** Help dialog open. */
  helpOpen: boolean;

  setPanelSizes: (sizes: [number, number, number]) => void;
  toggleSidebar: () => void;
  toggleGraphFullscreen: () => void;
  setGraphFullscreen: (v: boolean) => void;
  setCommandPaletteOpen: (v: boolean) => void;
  toggleCommandPalette: () => void;
  setHelpOpen: (v: boolean) => void;
  toggleHelp: () => void;
}

const DEFAULT_PANEL_SIZES: [number, number, number] = [24, 38, 38];

export const useWorkspaceStore = create<WorkspaceState>()(
  persist(
    (set) => ({
      panelSizes: DEFAULT_PANEL_SIZES,
      sidebarCollapsed: false,
      graphFullscreen: false,
      commandPaletteOpen: false,
      helpOpen: false,

      setPanelSizes: (sizes) => set({ panelSizes: sizes }),
      toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
      toggleGraphFullscreen: () => set((state) => ({ graphFullscreen: !state.graphFullscreen })),
      setGraphFullscreen: (v) => set({ graphFullscreen: v }),
      setCommandPaletteOpen: (v) => set({ commandPaletteOpen: v }),
      toggleCommandPalette: () =>
        set((state) => ({ commandPaletteOpen: !state.commandPaletteOpen })),
      setHelpOpen: (v) => set({ helpOpen: v }),
      toggleHelp: () => set((state) => ({ helpOpen: !state.helpOpen })),
    }),
    {
      name: STORAGE_KEYS.workspaceLayout,
      storage: createJSONStorage(() => localStorage),
      // Only persist layout, not transient UI state.
      partialize: (state) => ({
        panelSizes: state.panelSizes,
        sidebarCollapsed: state.sidebarCollapsed,
      }),
    },
  ),
);
