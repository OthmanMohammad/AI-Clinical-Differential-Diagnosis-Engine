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
  const [mobileGraphOpen, setMobileGraphOpen] = React.useState(false);

  const handleLayout = React.useCallback(
    (sizes: number[]) => {
      if (sizes.length === 3) {
        setPanelSizes([sizes[0]!, sizes[1]!, sizes[2]!]);
      }
    },
    [setPanelSizes],
  );

  // Mobile layout
  if (isMobile) {
    return (
      <>
        <main className="bg-background flex-1">
          <section aria-label="Clinical intake" className="border-border border-b p-3">
            {intake}
          </section>
          <section aria-label="Differential diagnosis" className="border-border border-b p-3">
            {results}
          </section>
          {/* Graph preview — non-interactive, just a visual */}
          <section aria-label="Reasoning graph" className="relative h-[60vh] min-h-[250px]">
            <div className="pointer-events-none h-full opacity-60">{graph}</div>
            <div className="absolute inset-0 flex items-center justify-center">
              <button
                type="button"
                onClick={() => setMobileGraphOpen(true)}
                className="bg-primary text-primary-foreground pointer-events-auto flex items-center gap-2 rounded-full px-6 py-3 text-sm font-medium shadow-xl"
              >
                <Maximize2 className="h-4 w-4" />
                Explore graph
              </button>
            </div>
          </section>
        </main>

        {/* Fullscreen graph overlay — completely separate from the page layout.
            Uses inline styles for bulletproof background coverage. */}
        {mobileGraphOpen && (
          <div
            style={{
              position: "fixed",
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              zIndex: 9999,
              backgroundColor: "hsl(var(--background))",
              touchAction: "none",
            }}
          >
            <div className="h-full w-full">{graph}</div>

            {/* Close button — top left */}
            <button
              type="button"
              onClick={() => setMobileGraphOpen(false)}
              className="absolute left-3 top-3 z-10 flex items-center gap-1.5 rounded-full bg-black/70 px-3 py-1.5 text-xs font-medium text-white shadow-lg"
            >
              <X className="h-3.5 w-3.5" />
              Close
            </button>

            {/* Zoom buttons — bottom right */}
            <div className="absolute bottom-8 right-3 z-10 flex flex-col gap-2">
              <button
                type="button"
                onClick={() =>
                  document.dispatchEvent(new CustomEvent("mooseglove:graph-zoom", { detail: 1.4 }))
                }
                className="flex h-11 w-11 items-center justify-center rounded-full bg-black/70 text-white shadow-lg"
                aria-label="Zoom in"
              >
                <Plus className="h-5 w-5" />
              </button>
              <button
                type="button"
                onClick={() =>
                  document.dispatchEvent(new CustomEvent("mooseglove:graph-zoom", { detail: 0.7 }))
                }
                className="flex h-11 w-11 items-center justify-center rounded-full bg-black/70 text-white shadow-lg"
                aria-label="Zoom out"
              >
                <Minus className="h-5 w-5" />
              </button>
            </div>
          </div>
        )}
      </>
    );
  }

  // Desktop layout — unchanged
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
