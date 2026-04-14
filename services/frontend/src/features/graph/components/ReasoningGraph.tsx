/**
 * AntV G6 v5 reasoning graph.
 *
 * Responsibilities:
 *  - Instantiate a G6 Graph keyed to the current response
 *  - Apply clinical-entity color theming from CSS variables
 *  - Handle interactions: hover, click, search, layout change, export
 *  - Highlight the path of the top (or hovered) diagnosis
 *
 * The component is memoized so re-renders don't thrash the canvas.
 */

import * as React from "react";
import { Graph } from "@antv/g6";
import { logger } from "@/lib/logger";

import { getLayoutConfig, type LayoutType } from "@/features/graph/config/layouts";
import {
  getBackgroundColor,
  getBorderColor,
  getEntityColors,
  getForegroundColor,
  getMutedColor,
  getPrimaryColor,
} from "@/features/graph/config/theme";
import { formatEdgeLabel } from "@/features/graph/config/edgeTypes";
import type { GraphEdge, GraphNode, GraphNodeType } from "@/types/api";
import { useTheme } from "@/hooks/useTheme";

export interface ReasoningGraphHandle {
  fitView: () => void;
  zoomIn: () => void;
  zoomOut: () => void;
  focusNode: (id: string) => void;
  exportImage: (format: "png" | "svg") => void;
  setLayout: (layout: LayoutType) => void;
  setHiddenTypes: (types: Set<string>) => void;
  highlightPath: (names: string[] | null) => void;
}

interface ReasoningGraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  /** Names of nodes to emphasize (the top diagnosis path). */
  topPath?: string[];
  /** Hidden node types (toggled via legend). */
  hiddenTypes?: Set<string>;
  /** Selected node (opens the detail drawer). */
  onNodeClick?: (node: GraphNode) => void;
  className?: string;
}

const ENTITY_ORDER: GraphNodeType[] = [
  "Disease",
  "Symptom",
  "Gene",
  "Drug",
  "Phenotype",
  "Anatomy",
];

function isEntityType(t: string): t is GraphNodeType {
  return ENTITY_ORDER.includes(t as GraphNodeType);
}

export const ReasoningGraph = React.forwardRef<ReasoningGraphHandle, ReasoningGraphProps>(
  function ReasoningGraph(
    { nodes, edges, topPath, hiddenTypes, onNodeClick, className },
    ref,
  ) {
    const containerRef = React.useRef<HTMLDivElement>(null);
    const graphRef = React.useRef<Graph | null>(null);
    const { resolvedTheme } = useTheme();
    const [layout, setLayoutState] = React.useState<LayoutType>("force");

    // Keep current callbacks/values in refs so the G6 instance can read them
    // without needing to be rebuilt on every render.
    const onNodeClickRef = React.useRef(onNodeClick);
    const hiddenTypesRef = React.useRef(hiddenTypes);
    const topPathRef = React.useRef(topPath);
    React.useEffect(() => {
      onNodeClickRef.current = onNodeClick;
    }, [onNodeClick]);
    React.useEffect(() => {
      hiddenTypesRef.current = hiddenTypes;
    }, [hiddenTypes]);
    React.useEffect(() => {
      topPathRef.current = topPath;
    }, [topPath]);

    /** Build the G6 data payload from props. */
    const buildData = React.useCallback(() => {
      const colors = getEntityColors();
      const pathSet = new Set(
        (topPathRef.current ?? []).map((n) => n.toLowerCase()),
      );
      const hidden = hiddenTypesRef.current ?? new Set<string>();

      const g6Nodes = nodes.map((n) => {
        const isHidden = hidden.has(n.type);
        const isOnPath = pathSet.has(n.name.toLowerCase());
        const entityType = isEntityType(n.type) ? n.type : "Disease";
        const color = colors[entityType];
        return {
          id: n.id,
          data: {
            name: n.name,
            entityType: n.type,
            onPath: isOnPath,
            hidden: isHidden,
          },
          style: {
            size: isOnPath ? 52 : 40,
            fill: color.fill,
            stroke: color.stroke,
            lineWidth: isOnPath ? 2.5 : 1.5,
            labelText: truncateLabel(n.name, 22),
            labelFill: getForegroundColor(),
            labelFontSize: 11,
            labelFontWeight: isOnPath ? 600 : 400,
            labelPlacement: "bottom" as const,
            labelOffsetY: 6,
            labelBackground: true,
            labelBackgroundFill: getBackgroundColor(),
            labelBackgroundFillOpacity: 0.75,
            labelBackgroundPadding: [1, 4, 1, 4] as [number, number, number, number],
            labelBackgroundRadius: 3,
            visibility: isHidden ? "hidden" : "visible",
            cursor: "pointer",
          },
        };
      });

      const g6Edges = edges
        .filter((e) => {
          const src = nodes.find((n) => n.id === e.source);
          const tgt = nodes.find((n) => n.id === e.target);
          if (!src || !tgt) return false;
          if (hidden.has(src.type) || hidden.has(tgt.type)) return false;
          return true;
        })
        .map((e, i) => {
          const src = nodes.find((n) => n.id === e.source);
          const tgt = nodes.find((n) => n.id === e.target);
          const onPath =
            src &&
            tgt &&
            pathSet.has(src.name.toLowerCase()) &&
            pathSet.has(tgt.name.toLowerCase());
          return {
            id: `e-${i}`,
            source: e.source,
            target: e.target,
            data: { type: e.type, onPath },
            style: {
              stroke: onPath ? getPrimaryColor() : getMutedColor(),
              lineWidth: onPath ? 2.5 : 1,
              strokeOpacity: onPath ? 0.9 : 0.45,
              endArrow: true,
              endArrowSize: 6,
            },
          };
        });

      return { nodes: g6Nodes, edges: g6Edges };
    }, [nodes, edges]);

    /** Initialise the graph once the container is mounted. */
    React.useEffect(() => {
      const container = containerRef.current;
      if (!container) return;

      logger.debug("graph.init", { nodes: nodes.length, edges: edges.length });

      const data = buildData();

      const graph = new Graph({
        container,
        background: getBackgroundColor(),
        autoFit: "view",
        padding: 24,
        data,
        node: {
          style: {} as Record<string, unknown>,
          state: {
            hover: {
              lineWidth: 3,
              shadowBlur: 12,
              shadowColor: getPrimaryColor(),
            },
            selected: {
              lineWidth: 3,
              stroke: getPrimaryColor(),
              shadowBlur: 16,
              shadowColor: getPrimaryColor(),
            },
            inactive: {
              fillOpacity: 0.2,
              strokeOpacity: 0.2,
              labelFillOpacity: 0.2,
            },
          },
        },
        edge: {
          style: {
            type: "quadratic",
            curveOffset: 18,
          } as Record<string, unknown>,
          state: {
            hover: {
              stroke: getPrimaryColor(),
              strokeOpacity: 1,
              lineWidth: 2,
            },
            active: {
              stroke: getPrimaryColor(),
              lineWidth: 2.5,
              strokeOpacity: 1,
            },
            inactive: {
              strokeOpacity: 0.08,
            },
          },
        },
        layout: getLayoutConfig(layout),
        behaviors: [
          "drag-canvas",
          "zoom-canvas",
          "drag-element",
          {
            type: "hover-activate",
            degree: 1,
            state: "hover",
            inactiveState: "inactive",
          },
          {
            type: "click-select",
            state: "selected",
            multiple: false,
          },
        ],
        plugins: [
          {
            type: "minimap",
            size: [160, 100],
            className: "pathodx-minimap",
            position: "right-bottom",
          },
          {
            type: "tooltip",
            trigger: "hover",
            enable: (evt: unknown, items: unknown[]): boolean =>
              items.length > 0 &&
              typeof (evt as { itemType?: string }).itemType === "string" &&
              (evt as { itemType: string }).itemType === "edge",
            getContent: (_evt: unknown, items: unknown[]) => {
              const edge = items[0] as { data?: { type?: string } } | undefined;
              const type = edge?.data?.type;
              if (!type) return "";
              return `<div style="font-size: 11px; font-family: var(--font-sans)">${formatEdgeLabel(type)}</div>`;
            },
          },
        ],
      });

      graphRef.current = graph;

      // Node click handler
      graph.on("node:click", (e: { target: { id: string } }) => {
        const nodeId = e.target.id;
        const node = nodes.find((n) => n.id === nodeId);
        if (node) {
          onNodeClickRef.current?.(node);
          logger.debug("graph.node_click", { id: nodeId, name: node.name });
        }
      });

      void graph.render().catch((err: Error) => {
        logger.error("graph.render_failed", { error: err.message });
      });

      const handleResize = () => {
        graph.resize();
      };
      window.addEventListener("resize", handleResize);

      return () => {
        window.removeEventListener("resize", handleResize);
        graph.destroy();
        graphRef.current = null;
        logger.debug("graph.destroyed");
      };
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [nodes, edges]);

    // Re-render data when nodes/edges change without full teardown
    // (handled inside the main effect; we rebuild on data change).

    // Re-apply layout when it changes
    React.useEffect(() => {
      const graph = graphRef.current;
      if (!graph) return;
      void graph
        .setLayout(getLayoutConfig(layout))
        .then(() => graph.layout())
        .catch((err: Error) =>
          logger.warn("graph.layout_failed", { error: err.message }),
        );
    }, [layout]);

    // Re-theme when theme changes — rebuild node/edge styles
    React.useEffect(() => {
      const graph = graphRef.current;
      if (!graph) return;
      const data = buildData();
      graph.setData(data);
      graph.setOptions({ background: getBackgroundColor() });
      void graph.render().catch((err: Error) =>
        logger.warn("graph.retheme_failed", { error: err.message }),
      );
    }, [resolvedTheme, buildData]);

    // Expose imperative handle
    React.useImperativeHandle(
      ref,
      () => ({
        fitView: () => {
          void graphRef.current?.fitView();
        },
        zoomIn: () => {
          void graphRef.current?.zoomBy(1.2);
        },
        zoomOut: () => {
          void graphRef.current?.zoomBy(0.8);
        },
        focusNode: (id: string) => {
          const graph = graphRef.current;
          if (!graph) return;
          void graph
            .focusElement(id, true)
            .catch((err: Error) =>
              logger.warn("graph.focus_failed", { error: err.message }),
            );
        },
        exportImage: (format: "png" | "svg") => {
          const graph = graphRef.current;
          if (!graph) return;
          try {
            const dataUrl = graph.toDataURL({ type: `image/${format}` });
            const link = document.createElement("a");
            link.download = `pathodx-graph-${Date.now()}.${format}`;
            link.href = dataUrl as unknown as string;
            document.body.appendChild(link);
            link.click();
            link.remove();
          } catch (err) {
            logger.warn("graph.export_failed", { error: (err as Error).message });
          }
        },
        setLayout: (next: LayoutType) => setLayoutState(next),
        setHiddenTypes: () => {
          // hiddenTypes is consumed via ref and triggers data rebuild via parent
        },
        highlightPath: () => {
          // Re-render via parent prop change
        },
      }),
      [],
    );

    return <div ref={containerRef} className={className} style={{ width: "100%", height: "100%" }} />;
  },
);

function truncateLabel(s: string, max: number): string {
  if (s.length <= max) return s;
  return `${s.slice(0, max - 1)}…`;
}
