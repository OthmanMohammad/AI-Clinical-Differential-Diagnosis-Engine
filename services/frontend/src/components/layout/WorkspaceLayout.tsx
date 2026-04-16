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
  // Mobile fullscreen graph: covers entire viewport, touch-action: none
  // so pinch/drag go to the graph canvas. Floating controls in corners.
  // ------------------------------------------------------------------
  if (isMobile && mobileGraphExpanded) {
    return (
      <div
        className="bg-background fixed inset-0 z-50 flex flex-col"
        style={{ touchAction: "none" }}
      >
        {/* Graph fills the screen */}
        <div className="relative flex-1">
          {graph}

          {/* Floating close button — top right, above the graph toolbar */}
          <button
            type="button"
            onClick={() => setMobileGraphExpanded(false)}
            className="bg-background/90 border-border absolute right-3 top-3 z-20 flex h-8 w-8 items-center justify-center rounded-full border shadow-md backdrop-blur-sm"
            aria-label="Close fullscreen"
          >
            <X className="h-4 w-4" />
          </button>

          {/* Floating zoom controls — bottom right */}
          <div className="absolute bottom-4 right-3 z-20 flex flex-col gap-1.5">
            <button
              type="button"
              onClick={() => {
                // Dispatch a custom zoom-in event the graph can pick up
                document.dispatchEvent(new CustomEvent("mooseglove:graph-zoom", { detail: 1.3 }));
              }}
              className="bg-background/90 border-border flex h-9 w-9 items-center justify-center rounded-full border shadow-md backdrop-blur-sm"
              aria-label="Zoom in"
            >
              <Plus className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => {
                document.dispatchEvent(new CustomEvent("mooseglove:graph-zoom", { detail: 0.7 }));
              }}
              className="bg-background/90 border-border flex h-9 w-9 items-center justify-center rounded-full border shadow-md backdrop-blur-sm"
              aria-label="Zoom out"
            >
              <Minus className="h-4 w-4" />
            </button>
          </div>

          {/* Hint text — bottom left, fades after 3s */}
          <MobileHint />
        </div>
      </div>
    );
  }

  // ------------------------------------------------------------------
  // Mobile: single-column page scroll. Graph section is a static
  // preview with an overlay blocking interaction.
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

        {/* Graph preview — pointer-events: none blocks all interaction.
            The overlay button has pointer-events: auto so it's tappable. */}
        <section aria-label="Reasoning graph" className="relative h-[70vh] min-h-[300px]">
          <div className="pointer-events-none h-full">{graph}</div>
          <button
            type="button"
            onClick={() => setMobileGraphExpanded(true)}
            className="bg-primary text-primary-foreground pointer-events-auto absolute bottom-4 left-1/2 z-10 flex -translate-x-1/2 items-center gap-2 rounded-full px-5 py-2.5 text-sm font-medium shadow-lg"
          >
            <Maximize2 className="h-4 w-4" />
            Explore graph
          </button>
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

/** Hint that fades out after 3 seconds. */
function MobileHint() {
  const [visible, setVisible] = React.useState(true);
  React.useEffect(() => {
    const t = setTimeout(() => setVisible(false), 3000);
    return () => clearTimeout(t);
  }, []);
  if (!visible) return null;
  return (
    <div className="bg-background/80 text-muted-foreground absolute bottom-4 left-3 z-20 rounded-full px-3 py-1.5 text-xs backdrop-blur-sm transition-opacity">
      Pinch to zoom, drag to pan
    </div>
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
