/**
 * G6 layout presets. Each returns a config object ready for `graph.setLayout`.
 */

export type LayoutType = "force" | "radial" | "dagre" | "concentric" | "grid";

export const LAYOUT_LABELS: Record<LayoutType, string> = {
  force: "Force",
  radial: "Radial",
  dagre: "Hierarchical",
  concentric: "Concentric",
  grid: "Grid",
};

export function getLayoutConfig(type: LayoutType): Record<string, unknown> {
  switch (type) {
    case "force":
      return {
        type: "force",
        preventOverlap: true,
        nodeSize: 56,
        linkDistance: 110,
        nodeStrength: -220,
        edgeStrength: 0.35,
        collideStrength: 0.9,
        alpha: 0.5,
        alphaDecay: 0.03,
      };
    case "radial":
      return {
        type: "radial",
        unitRadius: 120,
        preventOverlap: true,
        nodeSize: 56,
        maxPreventOverlapIteration: 200,
      };
    case "dagre":
      return {
        type: "dagre",
        rankdir: "LR",
        nodesep: 24,
        ranksep: 72,
      };
    case "concentric":
      return {
        type: "concentric",
        preventOverlap: true,
        nodeSize: 56,
        minNodeSpacing: 30,
      };
    case "grid":
      return {
        type: "grid",
        preventOverlap: true,
        nodeSize: 56,
      };
  }
}
