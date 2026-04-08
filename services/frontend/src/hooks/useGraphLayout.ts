/** Hook for auto-layouting graph nodes using dagre. */

import { useMemo } from "react";
import dagre from "dagre";
import type { GraphNode, GraphEdge } from "@/types/api";
import type { Node, Edge } from "@xyflow/react";

const NODE_WIDTH = 180;
const NODE_HEIGHT = 50;

const NODE_COLORS: Record<string, string> = {
  Disease: "#7F77DD",
  Symptom: "#888780",
  Gene: "#1D9E75",
  Drug: "#BA7517",
  Phenotype: "#378ADD",
  Anatomy: "#2D9E5B",
};

export function useGraphLayout(
  graphNodes: GraphNode[],
  graphEdges: GraphEdge[],
  topDiagnosisPath: string[],
) {
  return useMemo(() => {
    if (!graphNodes.length) return { nodes: [], edges: [] };

    const g = new dagre.graphlib.Graph();
    g.setDefaultEdgeLabel(() => ({}));
    g.setGraph({ rankdir: "LR", nodesep: 60, ranksep: 120 });

    // Build a set of highlight node IDs from top diagnosis path
    const highlightNames = new Set(topDiagnosisPath.map((n) => n.toLowerCase()));

    // Add nodes
    graphNodes.forEach((node) => {
      g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
    });

    // Add edges
    graphEdges.forEach((edge) => {
      if (g.hasNode(edge.source) && g.hasNode(edge.target)) {
        g.setEdge(edge.source, edge.target);
      }
    });

    dagre.layout(g);

    // Convert to React Flow format
    const rfNodes: Node[] = graphNodes.map((node) => {
      const pos = g.node(node.id);
      const isHighlighted = highlightNames.has(node.name.toLowerCase());
      const color = NODE_COLORS[node.type] ?? "#666";

      return {
        id: node.id,
        type: "default",
        position: {
          x: (pos?.x ?? 0) - NODE_WIDTH / 2,
          y: (pos?.y ?? 0) - NODE_HEIGHT / 2,
        },
        data: {
          label: node.name,
          nodeType: node.type,
        },
        style: {
          background: isHighlighted ? color : `${color}33`,
          color: isHighlighted ? "#fff" : "#ccc",
          border: `2px solid ${color}`,
          borderRadius: "8px",
          padding: "8px 12px",
          fontSize: "12px",
          fontWeight: isHighlighted ? 700 : 400,
          width: NODE_WIDTH,
        },
      };
    });

    const rfEdges: Edge[] = graphEdges
      .filter((e) => g.hasNode(e.source) && g.hasNode(e.target))
      .map((edge, i) => ({
        id: `e-${i}`,
        source: edge.source,
        target: edge.target,
        label: edge.type.replace(/_/g, " "),
        style: { stroke: "#555" },
        labelStyle: { fill: "#999", fontSize: 10 },
        animated: false,
      }));

    return { nodes: rfNodes, edges: rfEdges };
  }, [graphNodes, graphEdges, topDiagnosisPath]);
}
