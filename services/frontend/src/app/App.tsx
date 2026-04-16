/**
 * Application shell — top bar, sidebar, workspace, footer, and global UI
 * (command palette, help dialog). This is the only component that owns
 * cross-feature wiring.
 */

import * as React from "react";
import { toast } from "sonner";
import { useQuery } from "@tanstack/react-query";

import { TopBar } from "@/components/layout/TopBar";
import { Sidebar } from "@/components/layout/Sidebar";
import { Footer } from "@/components/layout/Footer";
import { WorkspaceLayout } from "@/components/layout/WorkspaceLayout";
import { CommandPalette } from "@/features/command-palette/CommandPalette";
import { HelpDialog } from "@/features/command-palette/HelpDialog";
import { ClinicalForm } from "@/features/diagnosis/components/ClinicalForm";
import { ResultsPanel } from "@/features/diagnosis/components/ResultsPanel";
import { GraphPanel } from "@/features/graph/components/GraphPanel";
import { useDiagnosis } from "@/features/diagnosis/hooks/useDiagnosis";
import { useIntakeStore } from "@/features/diagnosis/store/intake";
import { useGlobalShortcuts } from "@/hooks/useKeyboardShortcuts";
import { api, ApiError } from "@/lib/api";
import { QUERY_KEYS } from "@/lib/constants";
import { logger } from "@/lib/logger";

export function App() {
  // Global keyboard bindings
  useGlobalShortcuts();

  // Diagnosis pipeline
  const { isLoading, data, error, stages, run } = useDiagnosis();
  const toPayload = useIntakeStore((s) => s.toPayload);

  // Cross-panel highlight state
  const [highlightedDiagnosis, setHighlightedDiagnosis] = React.useState<string | null>(null);

  // Backend health check (runs in background, drives the status dot)
  const healthQuery = useQuery({
    queryKey: QUERY_KEYS.health,
    queryFn: () => api.health(),
    retry: 0,
    refetchInterval: 30_000,
    refetchOnMount: true,
  });

  const connectionStatus: "connected" | "disconnected" | "checking" = healthQuery.isLoading
    ? "checking"
    : healthQuery.isError
      ? "disconnected"
      : "connected";

  // Surface API errors as toasts
  React.useEffect(() => {
    if (!error) return;
    const message = error instanceof ApiError ? `${error.status}: ${error.message}` : error.message;
    toast.error("Diagnosis failed", { description: message });
    logger.warn("app.diagnosis_error_toast", { message });
  }, [error]);

  const handleSubmit = React.useCallback(async () => {
    const payload = toPayload();
    logger.info("app.submit", { symptoms: payload.symptoms });
    await run(payload);
  }, [run, toPayload]);

  // The top diagnosis's graph path — used to highlight the G6 graph.
  const topPath: string[] | undefined = React.useMemo(() => {
    if (highlightedDiagnosis && data) {
      const match = data.diagnoses.find((d) => d.disease_name === highlightedDiagnosis);
      if (match && match.graph_path.length > 0) return match.graph_path;
    }
    return data?.diagnoses[0]?.graph_path;
  }, [data, highlightedDiagnosis]);

  return (
    <div className="bg-background text-foreground flex min-h-screen w-screen flex-col overflow-x-hidden md:h-screen md:overflow-hidden">
      <TopBar connectionStatus={connectionStatus} />
      <div className="flex min-h-0 flex-1">
        <Sidebar />
        <WorkspaceLayout
          intake={<ClinicalForm isSubmitting={isLoading} onSubmit={handleSubmit} />}
          results={
            <ResultsPanel
              isLoading={isLoading}
              data={data}
              error={error}
              stages={stages}
              onRetry={handleSubmit}
              onHighlightDiagnosis={setHighlightedDiagnosis}
              highlightedDiagnosis={highlightedDiagnosis}
            />
          }
          graph={<GraphPanel response={data} topPath={topPath} />}
          graphNodeCount={data?.graph_nodes?.length ?? 0}
          graphEdgeCount={data?.graph_edges?.length ?? 0}
        />
      </div>
      <Footer
        modelUsed={data?.model_used}
        promptVersion={data?.prompt_version}
        requestId={data?.request_id}
      />

      <CommandPalette />
      <HelpDialog />
    </div>
  );
}
