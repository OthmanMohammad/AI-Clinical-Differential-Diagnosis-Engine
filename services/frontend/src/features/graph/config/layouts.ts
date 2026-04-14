/**
 * G6 layout presets. Each returns a config object ready for `graph.setLayout`.
 *
 * Defaults are tuned for biomedical knowledge graphs in the 30-100 node range:
 *  - enough repulsion that nodes never overlap
 *  - enough alpha decay that the simulation settles within a second
 *  - generous label clearance via large effective node sizes
 */

export type LayoutType = "radial" | "force" | "dagre" | "concentric" | "grid";

export const LAYOUT_LABELS: Record<LayoutType, string> = {
  radial: "Radial",
  force: "Force",
  dagre: "Hierarchical",
  concentric: "Concentric",
  grid: "Grid",
};

/** The default layout used on first render — radial reads best for medical KGs. */
export const DEFAULT_LAYOUT: LayoutType = "radial";

export function getLayoutConfig(type: LayoutType): Record<string, unknown> {
  switch (type) {
    case "radial":
      return {
        type: "radial",
        unitRadius: 140,
        preventOverlap: true,
        nodeSize: 80,
        maxPreventOverlapIteration: 240,
        focusNode: 0,
        linkDistance: 130,
        strictRadial: false,
      };
    case "force":
      return {
        type: "force",
        preventOverlap: true,
        nodeSize: 80,
        linkDistance: 160,
        nodeStrength: -550,
        edgeStrength: 0.3,
        collideStrength: 1.0,
        alpha: 0.3,
        alphaDecay: 0.05,
        alphaMin: 0.01,
      };
    case "dagre":
      return {
        type: "dagre",
        rankdir: "LR",
        nodesep: 32,
        ranksep: 96,
        controlPoints: true,
      };
    case "concentric":
      return {
        type: "concentric",
        preventOverlap: true,
        nodeSize: 80,
        minNodeSpacing: 36,
        equidistant: true,
      };
    case "grid":
      return {
        type: "grid",
        preventOverlap: true,
        nodeSize: 80,
        condense: false,
      };
  }
}
