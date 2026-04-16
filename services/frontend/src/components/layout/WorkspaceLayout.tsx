import * as React from "react";
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

  const handleLayout = React.useCallback(
    (sizes: number[]) => {
      if (sizes.length === 3) {
        setPanelSizes([sizes[0]!, sizes[1]!, sizes[2]!]);
      }
    },
    [setPanelSizes],
  );

  // Mobile: simple vertical scroll layout, no resizable panels
  if (isMobile) {
    return (
      <main className="bg-background flex min-h-0 flex-1 flex-col overflow-y-auto">
        <WorkspacePanel label="Clinical intake">{intake}</WorkspacePanel>
        <div className="bg-border h-px shrink-0" />
        <WorkspacePanel label="Differential diagnosis">{results}</WorkspacePanel>
        <div className="bg-border h-px shrink-0" />
        <WorkspacePanel label="Reasoning graph" noPadding>
          <div className="h-[50vh]">{graph}</div>
        </WorkspacePanel>
      </main>
    );
  }

  // Desktop: resizable 3-panel horizontal layout
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
                <WorkspacePanel label="Clinical intake">{intake}</WorkspacePanel>
              </Panel>
              <ResizeHandle />
              <Panel defaultSize={panelSizes[1]} minSize={18} className="min-w-0">
                <WorkspacePanel label="Differential diagnosis">{results}</WorkspacePanel>
              </Panel>
              <ResizeHandle />
              <Panel defaultSize={panelSizes[2]} minSize={18} className="min-w-0">
                <WorkspacePanel label="Reasoning graph" noPadding>
                  {graph}
                </WorkspacePanel>
              </Panel>
            </PanelGroup>
          </motion.div>
        )}
      </AnimatePresence>
    </main>
  );
}

interface WorkspacePanelProps {
  label: string;
  children: React.ReactNode;
  noPadding?: boolean;
}

function WorkspacePanel({ label, children, noPadding }: WorkspacePanelProps) {
  return (
    <section
      aria-label={label}
      className={cn(
        "bg-background flex min-w-0 flex-col overflow-hidden",
        "h-auto md:h-full",
        !noPadding && "p-3 md:p-4",
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
