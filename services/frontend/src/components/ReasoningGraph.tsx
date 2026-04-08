/** Right panel — Interactive reasoning graph using React Flow. */

import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { useState } from "react";
import type { GraphNode, GraphEdge } from "@/types/api";
import { useGraphLayout } from "@/hooks/useGraphLayout";

interface ReasoningGraphProps {
  graphNodes: GraphNode[];
  graphEdges: GraphEdge[];
  topDiagnosisPath: string[];
}

const MINIMAP_COLORS: Record<string, string> = {
  Disease: "#7F77DD",
  Symptom: "#888780",
  Gene: "#1D9E75",
  Drug: "#BA7517",
  Phenotype: "#378ADD",
  Anatomy: "#2D9E5B",
};

export default function ReasoningGraph({
  graphNodes,
  graphEdges,
  topDiagnosisPath,
}: ReasoningGraphProps) {
  const { nodes, edges } = useGraphLayout(graphNodes, graphEdges, topDiagnosisPath);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);

  const onNodeClick: NodeMouseHandler = (_event, node) => {
    const graphNode = graphNodes.find((n) => n.id === node.id);
    setSelectedNode(graphNode ?? null);
  };

  if (!graphNodes.length) {
    return (
      <div className="flex items-center justify-center h-full text-gray-600 text-sm">
        Graph visualization will appear here after analysis.
      </div>
    );
  }

  return (
    <div className="h-full relative">
      <h2 className="text-lg font-semibold text-white mb-2">Reasoning Graph</h2>

      {/* Legend */}
      <div className="flex flex-wrap gap-2 mb-2">
        {Object.entries(MINIMAP_COLORS).map(([type, color]) => (
          <span
            key={type}
            className="inline-flex items-center gap-1 text-xs text-gray-400"
          >
            <span
              className="w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: color }}
            />
            {type}
          </span>
        ))}
      </div>

      <div className="h-[calc(100%-80px)] border border-gray-800 rounded-lg overflow-hidden bg-gray-900">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodeClick={onNodeClick}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.3}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#333" gap={20} />
          <Controls
            showInteractive={false}
            style={{ background: "#1a1a2e", borderColor: "#333" }}
          />
          <MiniMap
            nodeColor={(node) => {
              const nodeType = node.data?.nodeType as string;
              return MINIMAP_COLORS[nodeType] ?? "#666";
            }}
            style={{ background: "#111" }}
          />
        </ReactFlow>
      </div>

      {/* Node detail card */}
      {selectedNode && (
        <div className="absolute bottom-4 left-4 bg-gray-800 border border-gray-700 rounded-lg p-3 max-w-xs shadow-xl">
          <div className="flex items-center justify-between mb-1">
            <span
              className="text-xs px-2 py-0.5 rounded"
              style={{
                backgroundColor: `${MINIMAP_COLORS[selectedNode.type] ?? "#666"}33`,
                color: MINIMAP_COLORS[selectedNode.type] ?? "#666",
              }}
            >
              {selectedNode.type}
            </span>
            <button
              onClick={() => setSelectedNode(null)}
              className="text-gray-500 hover:text-white text-sm"
            >
              x
            </button>
          </div>
          <h4 className="text-white text-sm font-medium">{selectedNode.name}</h4>
          <p className="text-xs text-gray-500 mt-1">ID: {selectedNode.id}</p>
        </div>
      )}
    </div>
  );
}
