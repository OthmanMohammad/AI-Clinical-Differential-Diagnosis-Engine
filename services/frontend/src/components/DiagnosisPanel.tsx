/** Center panel — Differential diagnosis results. */

import { motion } from "framer-motion";
import type { DiagnosisResponse } from "@/types/api";
import ConfidenceBar from "./ConfidenceBar";
import DisclaimerFooter from "./DisclaimerFooter";
import EmergencyBanner from "./EmergencyBanner";

interface DiagnosisPanelProps {
  data: DiagnosisResponse | null;
  isLoading: boolean;
  error: Error | null;
}

export default function DiagnosisPanel({ data, isLoading, error }: DiagnosisPanelProps) {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500 text-sm">
          <div className="animate-pulse">Analyzing patient data...</div>
          <div className="text-xs text-gray-600 mt-2">
            Running Graph RAG pipeline
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-900/30 border border-red-800 rounded-lg p-4">
        <h3 className="text-red-400 font-medium">Error</h3>
        <p className="text-red-300 text-sm mt-1">{error.message}</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-600 text-sm">
        Submit a clinical case to see differential diagnosis results.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-white">Differential Diagnosis</h2>

      {/* Emergency banner */}
      <EmergencyBanner emergency={data.emergency} />

      {/* Warnings */}
      {data.low_confidence && (
        <div className="bg-yellow-900/30 border border-yellow-800 rounded px-3 py-2 text-yellow-300 text-sm">
          Low confidence — all diagnoses scored below threshold. Consider additional clinical data.
        </div>
      )}
      {data.low_context && (
        <div className="bg-orange-900/30 border border-orange-800 rounded px-3 py-2 text-orange-300 text-sm">
          Limited graph context — fewer medical entities matched. Results may be incomplete.
        </div>
      )}
      {data.treatment_advice_stripped && (
        <div className="bg-blue-900/30 border border-blue-800 rounded px-3 py-2 text-blue-300 text-xs">
          Treatment advice was detected and removed from the output.
        </div>
      )}

      {/* Diagnoses */}
      {data.diagnoses.length > 0 ? (
        <div className="space-y-3">
          {data.diagnoses.map((dx, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.1 }}
              className="bg-gray-800/50 border border-gray-700 rounded-lg p-3"
            >
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500 font-mono">#{i + 1}</span>
                  <h3 className="text-white font-medium text-sm">{dx.disease_name}</h3>
                </div>
              </div>

              <ConfidenceBar
                confidence={dx.confidence}
                verified={dx.verified_in_graph}
              />

              <div className="mt-2">
                <p className="text-xs text-gray-500 mb-1">Evidence:</p>
                <ul className="space-y-0.5">
                  {dx.supporting_evidence.map((ev, j) => (
                    <li key={j} className="text-xs text-gray-400">
                      {ev}
                    </li>
                  ))}
                </ul>
              </div>

              {dx.graph_path.length > 0 && (
                <div className="mt-2">
                  <p className="text-xs text-gray-500">
                    Path: {dx.graph_path.join(" -> ")}
                  </p>
                </div>
              )}
            </motion.div>
          ))}
        </div>
      ) : (
        !data.emergency.triggered && (
          <p className="text-gray-500 text-sm">No diagnoses generated.</p>
        )
      )}

      {/* Reasoning summary */}
      {data.reasoning_summary && (
        <div className="bg-gray-800/30 rounded-lg p-3">
          <p className="text-xs text-gray-500 mb-1">Reasoning:</p>
          <p className="text-sm text-gray-300">{data.reasoning_summary}</p>
        </div>
      )}

      {/* Metadata */}
      <div className="flex gap-4 text-xs text-gray-600">
        {data.model_used && <span>Model: {data.model_used}</span>}
        {data.prompt_version && <span>Prompt: v{data.prompt_version}</span>}
        {data.llm_fallback && (
          <span className="text-yellow-600">Fallback model used</span>
        )}
      </div>

      {/* Disclaimer */}
      <DisclaimerFooter text={data.disclaimer} />
    </div>
  );
}
