/**
 * AntV G6 v5 reasoning graph.
 *
 * Owns a single Graph instance that lives across renders. Data is rebuilt
 * (and the graph re-rendered) whenever the inputs change — nodes, edges,
 * theme, hidden types, or the highlighted top diagnosis path.
 */

import * as React from "react";
import { Graph } from "@antv/g6";
import { logger } from "@/lib/logger";

import { getLayoutConfig, type LayoutType } from "@/features/graph/config/layouts";
import {
  getBackgroundColor,
  getEntityColors,
  getForegroundColor,
  getMutedColor,
  getPrimaryColor,
} from "@/features/graph/config/theme";
import type { GraphEdge, GraphNode, GraphNodeType } from "@/types/api";
import { useTheme } from "@/hooks/useTheme";

export interface ReasoningGraphHandle {
  fitView: () => void;
  zoomIn: () => void;
  zoomOut: () => void;
  focusNode: (id: string) => void;
  exportImage: (format: "png" | "svg") => Promise<void>;
  setLayout: (layout: LayoutType) => void;
}

interface ReasoningGraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  /** Names of nodes to emphasize (the top diagnosis path). */
  topPath?: string[];
  /** Hidden node types (toggled via legend). */
  hiddenTypes?: Set<string>;
  /** Currently active layout. */
  layout?: LayoutType;
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

/**
 * Safely invoke a graph method that may return a Promise OR a plain value.
 * G6 v5's API is inconsistent — some methods return promises, some are sync.
 */
function safeCall(label: string, fn: () => unknown): void {
  try {
    const result = fn();
    if (result && typeof (result as Promise<unknown>).then === "function") {
      (result as Promise<unknown>).catch((err: Error) => {
        logger.warn(`graph.${label}_failed`, { error: err.message });
      });
    }
  } catch (err) {
    logger.warn(`graph.${label}_failed`, { error: (err as Error).message });
  }
}

function truncateLabel(s: string, max: number): string {
  if (s.length <= max) return s;
  return `${s.slice(0, max - 1)}…`;
}

interface BuiltData {
  nodes: Array<Record<string, unknown>>;
  edges: Array<Record<string, unknown>>;
}

/** Pure data builder — no closures over component state.
 *
 * Hidden nodes are kept in the data set (so the layout engine remembers
 * their positions) but rendered with visibility: hidden. Toggling a type
 * back on then just makes the existing nodes visible in place, instead of
 * spawning fresh nodes at the origin.
 *
 * Edges that reference nodes outside the current node set are dropped —
 * the backend's graph traversal caps nodes and edges separately, so some
 * edges in the response point to nodes that didn't make the cap.
 */
function buildGraphData(
  nodes: GraphNode[],
  edges: GraphEdge[],
  hiddenTypes: Set<string>,
  topPath: string[] | undefined,
): BuiltData {
  const colors = getEntityColors();
  const fg = getForegroundColor();
  const bg = getBackgroundColor();
  const pathSet = new Set((topPath ?? []).map((n) => n.toLowerCase()));

  // Index nodes for fast lookup AND to reject dangling edges
  const nodeById = new Map<string, GraphNode>();
  for (const n of nodes) {
    nodeById.set(n.id, n);
  }

  const g6Nodes = nodes.map((n) => {
    const isHidden = hiddenTypes.has(n.type);
    const isOnPath = pathSet.has(n.name.toLowerCase());
    const entityType = isEntityType(n.type) ? n.type : "Disease";
    const color = colors[entityType];
    return {
      id: n.id,
      data: {
        name: n.name,
        entityType: n.type,
        onPath: isOnPath,
      },
      style: {
        size: isOnPath ? 56 : 38,
        fill: color.fill,
        stroke: color.stroke,
        lineWidth: isOnPath ? 3 : 1.5,
        labelText: truncateLabel(n.name, 24),
        labelFill: fg,
        labelFontSize: isOnPath ? 12 : 10,
        labelFontWeight: isOnPath ? 700 : 500,
        labelPlacement: "bottom" as const,
        labelOffsetY: 6,
        labelBackground: true,
        labelBackgroundFill: bg,
        labelBackgroundFillOpacity: 0.85,
        labelBackgroundPadding: [2, 5, 2, 5] as [number, number, number, number],
        labelBackgroundRadius: 3,
        cursor: "pointer",
        visibility: isHidden ? "hidden" : "visible",
      },
    };
  });

  const g6Edges = edges
    .filter((e) => nodeById.has(e.source) && nodeById.has(e.target))
    .map((e, i) => {
      const src = nodeById.get(e.source)!;
      const tgt = nodeById.get(e.target)!;
      const isHidden = hiddenTypes.has(src.type) || hiddenTypes.has(tgt.type);
      const onPath = pathSet.has(src.name.toLowerCase()) && pathSet.has(tgt.name.toLowerCase());
      return {
        id: `e-${i}`,
        source: e.source,
        target: e.target,
        data: { type: e.type, onPath },
        style: {
          stroke: onPath ? getPrimaryColor() : getMutedColor(),
          lineWidth: onPath ? 2.5 : 1,
          strokeOpacity: onPath ? 0.95 : 0.4,
          endArrow: true,
          endArrowSize: 6,
          visibility: isHidden ? "hidden" : "visible",
        },
      };
    });

  return { nodes: g6Nodes, edges: g6Edges };
}

export const ReasoningGraph = React.forwardRef<ReasoningGraphHandle, ReasoningGraphProps>(
  function ReasoningGraph(
    { nodes, edges, topPath, hiddenTypes, layout = "radial", onNodeClick, className },
    ref,
  ) {
    const containerRef = React.useRef<HTMLDivElement>(null);
    const graphRef = React.useRef<Graph | null>(null);
    const resizeObserverDebounce = React.useRef<ReturnType<typeof setTimeout> | null>(null);
    const { resolvedTheme } = useTheme();

    // Latest values exposed via refs so the G6 instance can read them
    // without rebuilding from scratch.
    const onNodeClickRef = React.useRef(onNodeClick);
    React.useEffect(() => {
      onNodeClickRef.current = onNodeClick;
    }, [onNodeClick]);

    const hidden = React.useMemo(() => hiddenTypes ?? new Set<string>(), [hiddenTypes]);

    /** Rebuild G6 data from the current props (and current theme CSS vars). */
    const data = React.useMemo(
      () => buildGraphData(nodes, edges, hidden, topPath),
      // resolvedTheme is intentionally a dep so the colors re-read on theme switch
      // eslint-disable-next-line react-hooks/exhaustive-deps
      [nodes, edges, hidden, topPath, resolvedTheme],
    );

    // ---- Initialize the graph once per (nodes, edges) change ----
    React.useEffect(() => {
      const container = containerRef.current;
      if (!container) return;
      if (nodes.length === 0) return;

      const isMobile = window.innerWidth < 768;
      logger.debug("graph.init", { nodes: nodes.length, edges: edges.length, isMobile });

      const graph = new Graph({
        container,
        // Transparent — let the container's CSS background show through so
        // theme switching works without re-instantiating the graph.
        background: "transparent",
        autoFit: "view",
        padding: 32,
        data,
        node: {
          state: isMobile
            ? {} // No hover/shadow states on mobile — saves GPU
            : {
                hover: {
                  lineWidth: 3,
                  shadowBlur: 14,
                  shadowColor: getPrimaryColor(),
                },
                selected: {
                  lineWidth: 3,
                  stroke: getPrimaryColor(),
                  shadowBlur: 18,
                  shadowColor: getPrimaryColor(),
                },
                inactive: {
                  fillOpacity: 0.18,
                  strokeOpacity: 0.18,
                  labelFillOpacity: 0.18,
                },
              },
        },
        edge: {
          style: isMobile
            ? ({} as Record<string, unknown>) // Straight lines on mobile — 3-4x faster
            : ({
                type: "quadratic",
                curveOffset: 16,
              } as Record<string, unknown>),
          state: {
            hover: {
              stroke: getPrimaryColor(),
              strokeOpacity: 1,
              lineWidth: 2,
            },
            inactive: {
              strokeOpacity: 0.06,
            },
          },
        },
        layout: getLayoutConfig(layout),
        // On mobile: remove drag-canvas and zoom-canvas entirely — we
        // handle all touch gestures ourselves (single-finger pan + two-
        // finger pinch zoom). This eliminates the "shift then zoom"
        // conflict where drag-canvas fires on the first finger before
        // the second finger lands.
        behaviors: isMobile
          ? [
              {
                type: "click-select",
                state: "selected",
                multiple: false,
              },
            ]
          : [
              "drag-canvas",
              { type: "zoom-canvas", sensitivity: 1.5 },
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
        // Minimap is expensive on mobile — skip it below md breakpoint.
        plugins:
          window.innerWidth >= 768
            ? [
                {
                  type: "minimap",
                  size: [160, 100],
                  className: "mooseglove-minimap",
                  position: "right-bottom",
                },
              ]
            : [],
      });

      graphRef.current = graph;

      graph.on("node:click", (e: { target: { id: string } }) => {
        const nodeId = e.target.id;
        const node = nodes.find((n) => n.id === nodeId);
        if (node) {
          onNodeClickRef.current?.(node);
          logger.debug("graph.node_click", { id: nodeId, name: node.name });
        }
      });

      safeCall("render", () => graph.render());

      // +/- button zoom events from the fullscreen overlay.
      const handleZoom = (e: Event) => {
        const factor = (e as CustomEvent<number>).detail;
        if (factor && typeof factor === "number") {
          safeCall("zoom", () => graph.zoomTo(graph.getZoom() * factor));
        }
      };
      document.addEventListener("mooseglove:graph-zoom", handleZoom);

      // ---- Mobile touch: full pan + pinch-zoom handler ----
      // We own ALL touch gestures on mobile (G6 behaviors are stripped).
      // Single finger = pan. Two fingers = pinch-zoom toward midpoint.
      let touchMode: "none" | "pan" | "pinch" = "none";
      let lastTouchX = 0;
      let lastTouchY = 0;
      let pinchStartDist = 0;
      let pinchStartZoom = 1;

      const handleTouchStart = (e: TouchEvent) => {
        if (e.touches.length === 2) {
          e.preventDefault();
          touchMode = "pinch";
          pinchStartDist = Math.hypot(
            e.touches[0]!.clientX - e.touches[1]!.clientX,
            e.touches[0]!.clientY - e.touches[1]!.clientY,
          );
          pinchStartZoom = graph.getZoom();
        } else if (e.touches.length === 1) {
          touchMode = "pan";
          lastTouchX = e.touches[0]!.clientX;
          lastTouchY = e.touches[0]!.clientY;
        }
      };

      const handleTouchMove = (e: TouchEvent) => {
        e.preventDefault();

        if (touchMode === "pinch" && e.touches.length === 2) {
          const dist = Math.hypot(
            e.touches[0]!.clientX - e.touches[1]!.clientX,
            e.touches[0]!.clientY - e.touches[1]!.clientY,
          );
          const midX = (e.touches[0]!.clientX + e.touches[1]!.clientX) / 2;
          const midY = (e.touches[0]!.clientY + e.touches[1]!.clientY) / 2;
          // Convert page coords to container-relative
          const rect = container.getBoundingClientRect();
          const scale = dist / pinchStartDist;
          void graph.zoomTo(pinchStartZoom * scale, [midX - rect.left, midY - rect.top]);
        } else if (touchMode === "pan" && e.touches.length === 1) {
          const dx = e.touches[0]!.clientX - lastTouchX;
          const dy = e.touches[0]!.clientY - lastTouchY;
          lastTouchX = e.touches[0]!.clientX;
          lastTouchY = e.touches[0]!.clientY;
          void (graph as unknown as { translate(dx: number, dy: number): unknown }).translate(
            dx,
            dy,
          );
        }
      };

      const handleTouchEnd = () => {
        touchMode = "none";
      };

      if (isMobile) {
        container.addEventListener("touchstart", handleTouchStart, { passive: false });
        container.addEventListener("touchmove", handleTouchMove, { passive: false });
        container.addEventListener("touchend", handleTouchEnd);
        container.addEventListener("touchcancel", handleTouchEnd);
      }

      // Track container size changes (panel resize, fullscreen toggle, etc.)
      // The window resize handler only fires on viewport changes — it
      // misses Workspace panel drags. ResizeObserver catches every layout
      // change to the graph container.
      const handleResize = () => safeCall("resize", () => graph.resize());
      window.addEventListener("resize", handleResize);

      const resizeObserver = new ResizeObserver(() => {
        // Debounce slightly so we don't thrash during a continuous drag
        if (resizeObserverDebounce.current) {
          clearTimeout(resizeObserverDebounce.current);
        }
        resizeObserverDebounce.current = setTimeout(() => {
          safeCall("resize_observer", () => graph.resize());
        }, 60);
      });
      resizeObserver.observe(container);

      return () => {
        container.removeEventListener("touchstart", handleTouchStart);
        container.removeEventListener("touchmove", handleTouchMove);
        container.removeEventListener("touchend", handleTouchEnd);
        container.removeEventListener("touchcancel", handleTouchEnd);
        document.removeEventListener("mooseglove:graph-zoom", handleZoom);
        window.removeEventListener("resize", handleResize);
        resizeObserver.disconnect();
        if (resizeObserverDebounce.current) {
          clearTimeout(resizeObserverDebounce.current);
          resizeObserverDebounce.current = null;
        }
        try {
          graph.destroy();
        } catch (err) {
          logger.debug("graph.destroy_failed", { error: (err as Error).message });
        }
        graphRef.current = null;
      };
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [nodes, edges]);

    // ---- Update data when memoized output changes (theme, hiddenTypes, topPath) ----
    React.useEffect(() => {
      const graph = graphRef.current;
      if (!graph) return;
      safeCall("set_data", () => graph.setData(data));
      // Just redraw — DON'T re-run layout. Hidden nodes keep their positions
      // so toggling them back on shows them in place.
      safeCall("redraw", () => graph.draw());
    }, [data]);

    // ---- Re-apply layout when it changes ----
    React.useEffect(() => {
      const graph = graphRef.current;
      if (!graph) return;
      safeCall("set_layout", () => graph.setLayout(getLayoutConfig(layout)));
      safeCall("layout", () => graph.layout());
    }, [layout]);

    // ---- Imperative handle exposed to parent ----
    React.useImperativeHandle(
      ref,
      () => ({
        fitView: () => {
          const graph = graphRef.current;
          if (!graph) return;
          safeCall("fit_view", () => graph.fitView());
        },
        zoomIn: () => {
          const graph = graphRef.current;
          if (!graph) return;
          safeCall("zoom_in", () => graph.zoomBy(1.2));
        },
        zoomOut: () => {
          const graph = graphRef.current;
          if (!graph) return;
          safeCall("zoom_out", () => graph.zoomBy(0.8));
        },
        focusNode: (id: string) => {
          const graph = graphRef.current;
          if (!graph) return;
          safeCall("focus_node", () => graph.focusElement(id, true));
        },
        exportImage: async (_format: "png" | "svg") => {
          const graph = graphRef.current;
          if (!graph) return;
          try {
            // G6 v5: toDataURL returns Promise<string>. Use mode "overall"
            // and pixelRatio 2 for retina-quality output.
            const result = graph.toDataURL({
              mode: "overall" as const,
              type: "image/png",
              encoderOptions: 1,
            } as Record<string, unknown>);
            /* eslint-disable @typescript-eslint/no-misused-promises, @typescript-eslint/no-unnecessary-type-assertion -- g6 toDataURL returns unknown | Promise<string> */
            const dataUrl =
              result && typeof (result as Promise<string>).then === "function"
                ? await (result as Promise<string>)
                : (result as string);
            /* eslint-enable @typescript-eslint/no-misused-promises, @typescript-eslint/no-unnecessary-type-assertion */

            if (!dataUrl || typeof dataUrl !== "string") {
              throw new Error("Empty data URL from graph");
            }

            const link = document.createElement("a");
            link.download = `mooseglove-graph-${Date.now()}.png`;
            link.href = dataUrl;
            document.body.appendChild(link);
            link.click();
            link.remove();
          } catch (err) {
            logger.warn("graph.export_failed", {
              error: (err as Error).message,
            });
            throw err;
          }
        },
        setLayout: () => {
          // Layout is now driven via the `layout` prop. This method is kept
          // for API compatibility but does nothing — parent should update prop.
        },
      }),
      [],
    );

    if (nodes.length === 0) {
      return <div className={className} />;
    }

    return (
      <div ref={containerRef} className={className} style={{ width: "100%", height: "100%" }} />
    );
  },
);
