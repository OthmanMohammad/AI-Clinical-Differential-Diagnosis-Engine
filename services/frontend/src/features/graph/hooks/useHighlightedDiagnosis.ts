import { create } from "zustand";

/**
 * Cross-panel state — which diagnosis is currently hovered/highlighted.
 * The DiagnosisCard pushes updates; the ReasoningGraph reads and dims
 * non-path nodes accordingly.
 */

interface HighlightState {
  highlightedDiagnosis: string | null;
  setHighlightedDiagnosis: (name: string | null) => void;
}

export const useHighlightStore = create<HighlightState>((set) => ({
  highlightedDiagnosis: null,
  setHighlightedDiagnosis: (name) => set({ highlightedDiagnosis: name }),
}));
