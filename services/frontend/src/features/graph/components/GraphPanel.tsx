/**
 * Wraps the G6 graph with toolbar, legend, search, and drawer.
 * This is the component the workspace renders in the right panel.
 */

import * as React from "react";
import { toast } from "sonner";

import { GraphToolbar } from "@/features/graph/components/GraphToolbar";
import { GraphLegend } from "@/features/graph/components/GraphLegend";
import { GraphSearch } from "@/features/graph/components/GraphSearch";
import { NodeDetailDrawer } from "@/features/graph/components/NodeDetailDrawer";
import {
  ReasoningGraph,
  type ReasoningGraphHandle,
} from "@/features/graph/components/ReasoningGraph";
import { GraphEmptyState } from "@/features/graph/components/GraphEmptyState";
import { useWorkspaceStore } from "@/features/diagnosis/store/workspace";
import { ENTITY_TYPES } from "@/lib/constants";
import { DEFAULT_LAYOUT, type LayoutType } from "@/features/graph/config/layouts";
import type { DiagnosisResponse, GraphNode } from "@/types/api";

interface GraphPanelProps {
  response: DiagnosisResponse | null;
  /** If set, the names of the top diagnosis's path (used for highlighting). */
  topPath?: string[];
}

export function GraphPanel({ response, topPath }: GraphPanelProps) {
  const graphRef = React.useRef<ReasoningGraphHandle>(null);
  const [layout, setLayout] = React.useState<LayoutType>(DEFAULT_LAYOUT);
  const [hiddenTypes, setHiddenTypes] = React.useState<Set<string>>(() => new Set());
  const [searchOpen, setSearchOpen] = React.useState(false);
  const [selectedNode, setSelectedNode] = React.useState<GraphNode | null>(null);

  const graphFullscreen = useWorkspaceStore((s) => s.graphFullscreen);
  const toggleFullscreen = useWorkspaceStore((s) => s.toggleGraphFullscreen);

  const handleLayoutChange = (next: LayoutType) => {
    setLayout(next);
  };

  const handleToggleType = (type: string) => {
    setHiddenTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  const handleExportPng = async () => {
    try {
      await graphRef.current?.exportImage("png");
      toast.success("Graph exported as PNG");
    } catch (err) {
      toast.error("Export failed", {
        description: (err as Error).message,
      });
    }
  };

  const handleSearchSelect = (id: string) => {
    graphRef.current?.focusNode(id);
    const node = response?.graph_nodes.find((n) => n.id === id);
    if (node) setSelectedNode(node);
  };

  const visibleTypes = React.useMemo(
    () => new Set(ENTITY_TYPES.filter((t) => !hiddenTypes.has(t))),
    [hiddenTypes],
  );

  const hasGraph = response && response.graph_nodes.length > 0;

  return (
    <div className="relative flex h-full min-h-0 flex-col">
      {!hasGraph ? (
        <GraphEmptyState />
      ) : (
        <>
          <ReasoningGraph
            ref={graphRef}
            nodes={response.graph_nodes}
            edges={response.graph_edges}
            topPath={topPath}
            hiddenTypes={hiddenTypes}
            layout={layout}
            onNodeClick={(node) => setSelectedNode(node)}
            className="h-full"
          />

          {/* Overlays */}
          <div className="pointer-events-none absolute inset-x-3 top-3 flex flex-wrap items-start justify-between gap-2">
            <GraphLegend
              visibleTypes={visibleTypes}
              onToggle={handleToggleType}
            />
            <GraphToolbar
              layout={layout}
              onLayoutChange={handleLayoutChange}
              onFit={() => graphRef.current?.fitView()}
              onZoomIn={() => graphRef.current?.zoomIn()}
              onZoomOut={() => graphRef.current?.zoomOut()}
              onSearch={() => setSearchOpen(true)}
              onExportPng={() => void handleExportPng()}
              onToggleFullscreen={toggleFullscreen}
              fullscreen={graphFullscreen}
            />
          </div>

          {/* Search popover positioned in the top-right */}
          <div className="pointer-events-none absolute right-3 top-16 flex justify-end">
            <GraphSearch
              nodes={response.graph_nodes}
              open={searchOpen}
              onClose={() => setSearchOpen(false)}
              onSelect={handleSearchSelect}
            />
          </div>

          <NodeDetailDrawer
            node={selectedNode}
            allNodes={response.graph_nodes}
            allEdges={response.graph_edges}
            onClose={() => setSelectedNode(null)}
          />
        </>
      )}
    </div>
  );
}
