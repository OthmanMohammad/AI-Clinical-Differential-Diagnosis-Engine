import * as React from "react";
import { Maximize2, Minus, Plus, X } from "lucide-react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { AnimatePresence, motion } from "framer-motion";

import { useWorkspaceStore } from "@/features/diagnosis/store/workspace";
import { cn } from "@/lib/utils";

interface WorkspaceLayoutProps {
  intake: React.ReactNode;
  results: React.ReactNode;
  graph: React.ReactNode;
}

/** True when viewport is below the md breakpoint (768px). */
function useIsMobile(): boolean {
  const [mobile, setMobile] = React.useState(
    typeof window !== "undefined" ? window.innerWidth < 768 : false,
  );
  React.useEffect(() => {
    const mq = window.matchMedia("(max-width: 767px)");
    const handler = (e: MediaQueryListEvent) => setMobile(e.matches);
    mq.addEventListener("change", handler);
    setMobile(mq.matches);
    return () => mq.removeEventListener("change", handler);
  }, []);
  return mobile;
}

export function WorkspaceLayout({ intake, results, graph }: WorkspaceLayoutProps) {
  const panelSizes = useWorkspaceStore((s) => s.panelSizes);
  const setPanelSizes = useWorkspaceStore((s) => s.setPanelSizes);
  const graphFullscreen = useWorkspaceStore((s) => s.graphFullscreen);
  const isMobile = useIsMobile();
  const [mobileGraphExpanded, setMobileGraphExpanded] = React.useState(false);

  const handleLayout = React.useCallback(
    (sizes: number[]) => {
      if (sizes.length === 3) {
        setPanelSizes([sizes[0]!, sizes[1]!, sizes[2]!]);
      }
    },
    [setPanelSizes],
  );

  // ------------------------------------------------------------------
  // Mobile: single-column page scroll. The graph section uses CSS-only
  // fullscreen (position: fixed when expanded) so the G6 instance
  // stays mounted and doesn't need to re-initialize.
  // ------------------------------------------------------------------
  if (isMobile) {
    return (
      <main className="bg-background flex-1">
        <section aria-label="Clinical intake" className="border-border border-b p-3">
          {intake}
        </section>

        <section aria-label="Differential diagnosis" className="border-border border-b p-3">
          {results}
        </section>

        {/* Graph section — transforms between preview and fullscreen via CSS.
            The G6 graph instance stays mounted in both modes (no re-init).
            ResizeObserver in the graph component handles the container resize. */}
        <section
          aria-label="Reasoning graph"
          className={cn(
            "relative",
            mobileGraphExpanded
              ? "bg-background fixed inset-0 z-50 h-screen w-screen"
              : "h-[70vh] min-h-[300px]",
          )}
          style={mobileGraphExpanded ? { touchAction: "none" } : undefined}
        >
          {/* Graph — interaction disabled in preview, enabled in fullscreen */}
          <div className={cn("h-full", !mobileGraphExpanded && "pointer-events-none")}>{graph}</div>

          {/* Preview mode: "Explore graph" button */}
          {!mobileGraphExpanded && (
            <button
              type="button"
              onClick={() => setMobileGraphExpanded(true)}
              className="bg-primary text-primary-foreground pointer-events-auto absolute bottom-4 left-1/2 z-10 flex -translate-x-1/2 items-center gap-2 rounded-full px-5 py-2.5 text-sm font-medium shadow-lg"
            >
              <Maximize2 className="h-4 w-4" />
              Explore graph
            </button>
          )}

          {/* Fullscreen mode: floating controls */}
          {mobileGraphExpanded && (
            <>
              {/* Close — top left to avoid overlapping the graph legend */}
              <button
                type="button"
                onClick={() => setMobileGraphExpanded(false)}
                className="bg-background/90 border-border absolute left-3 top-3 z-30 flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium shadow-md backdrop-blur-sm"
              >
                <X className="h-3.5 w-3.5" />
                Close
              </button>

              {/* Zoom controls — bottom right, above any footer */}
              <div className="absolute bottom-6 right-3 z-30 flex flex-col gap-1.5">
                <button
                  type="button"
                  onClick={() => {
                    document.dispatchEvent(
                      new CustomEvent("mooseglove:graph-zoom", { detail: 1.4 }),
                    );
                  }}
                  className="bg-background/90 border-border flex h-10 w-10 items-center justify-center rounded-full border shadow-md backdrop-blur-sm"
                  aria-label="Zoom in"
                >
                  <Plus className="h-5 w-5" />
                </button>
                <button
                  type="button"
                  onClick={() => {
                    document.dispatchEvent(
                      new CustomEvent("mooseglove:graph-zoom", { detail: 0.7 }),
                    );
                  }}
                  className="bg-background/90 border-border flex h-10 w-10 items-center justify-center rounded-full border shadow-md backdrop-blur-sm"
                  aria-label="Zoom out"
                >
                  <Minus className="h-5 w-5" />
                </button>
              </div>
            </>
          )}
        </section>
      </main>
    );
  }

  // ------------------------------------------------------------------
  // Desktop: resizable 3-panel horizontal layout
  // ------------------------------------------------------------------
  return (
    <main className="bg-background flex min-h-0 flex-1">
      <AnimatePresence mode="wait" initial={false}>
        {graphFullscreen ? (
          <motion.div
            key="fullscreen"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="min-w-0 flex-1"
          >
            {graph}
          </motion.div>
        ) : (
          <motion.div
            key="split"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="min-w-0 flex-1"
          >
            <PanelGroup
              direction="horizontal"
              onLayout={handleLayout}
              className="h-full"
              autoSaveId={undefined}
            >
              <Panel defaultSize={panelSizes[0]} minSize={16} maxSize={45} className="min-w-0">
                <DesktopPanel label="Clinical intake">{intake}</DesktopPanel>
              </Panel>
              <ResizeHandle />
              <Panel defaultSize={panelSizes[1]} minSize={18} className="min-w-0">
                <DesktopPanel label="Differential diagnosis">{results}</DesktopPanel>
              </Panel>
              <ResizeHandle />
              <Panel defaultSize={panelSizes[2]} minSize={18} className="min-w-0">
                <DesktopPanel label="Reasoning graph" noPadding>
                  {graph}
                </DesktopPanel>
              </Panel>
            </PanelGroup>
          </motion.div>
        )}
      </AnimatePresence>
    </main>
  );
}

/** Desktop panel: fixed height, internal scroll, padding. */
function DesktopPanel({
  label,
  children,
  noPadding,
}: {
  label: string;
  children: React.ReactNode;
  noPadding?: boolean;
}) {
  return (
    <section
      aria-label={label}
      className={cn(
        "bg-background flex h-full min-w-0 flex-col overflow-hidden",
        !noPadding && "p-4",
      )}
    >
      {children}
    </section>
  );
}

function ResizeHandle() {
  return (
    <PanelResizeHandle className="bg-border data-[resize-handle-active]:bg-primary group relative w-px outline-none transition-colors">
      <div className="absolute inset-y-0 -left-1 -right-1 cursor-col-resize" />
      <div className="bg-border group-hover:bg-primary/60 pointer-events-none absolute left-1/2 top-1/2 h-8 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full transition-colors" />
    </PanelResizeHandle>
  );
}
