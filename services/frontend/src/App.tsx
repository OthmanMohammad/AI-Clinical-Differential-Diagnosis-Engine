/** PathoDX — Main Application Shell (Three-Panel Layout). */

import { ReactFlowProvider } from "@xyflow/react";
import ClinicalForm from "@/components/ClinicalForm";
import DiagnosisPanel from "@/components/DiagnosisPanel";
import ReasoningGraph from "@/components/ReasoningGraph";
import { useDiagnosis } from "@/hooks/useDiagnosis";

export default function App() {
  const { mutate, data, isPending, error } = useDiagnosis();

  const topPath = data?.diagnoses?.[0]?.graph_path ?? [];

  return (
    <div className="min-h-screen bg-gray-950">
      {/* Header */}
      <header className="border-b border-gray-800 px-6 py-3">
        <div className="flex items-center justify-between max-w-[1800px] mx-auto">
          <div>
            <h1 className="text-xl font-bold text-white tracking-tight">
              PathoDX
            </h1>
            <p className="text-xs text-gray-500">
              AI Clinical Differential Diagnosis Engine
            </p>
          </div>
          <div className="flex items-center gap-4 text-xs text-gray-600">
            <span>Graph RAG + LLM</span>
            <span className="w-2 h-2 bg-green-500 rounded-full" title="API Connected" />
          </div>
        </div>
      </header>

      {/* Three-Panel Layout */}
      <main className="max-w-[1800px] mx-auto grid grid-cols-[340px_1fr_1fr] gap-4 p-4 h-[calc(100vh-60px)]">
        {/* Left Panel — Clinical Form */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 overflow-y-auto">
          <ClinicalForm
            onSubmit={(intake) => mutate(intake)}
            isLoading={isPending}
          />
        </div>

        {/* Center Panel — Diagnosis Results */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 overflow-y-auto">
          <DiagnosisPanel
            data={data ?? null}
            isLoading={isPending}
            error={error}
          />
        </div>

        {/* Right Panel — Reasoning Graph */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-2">
          <ReactFlowProvider>
            <ReasoningGraph
              graphNodes={data?.graph_nodes ?? []}
              graphEdges={data?.graph_edges ?? []}
              topDiagnosisPath={topPath}
            />
          </ReactFlowProvider>
        </div>
      </main>
    </div>
  );
}
