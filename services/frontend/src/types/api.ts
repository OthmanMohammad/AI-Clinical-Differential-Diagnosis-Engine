/** API request/response types — mirrors backend Pydantic models. */

export interface Vitals {
  temperature_c?: number | null;
  heart_rate?: number | null;
  systolic_bp?: number | null;
  diastolic_bp?: number | null;
  spo2?: number | null;
  respiratory_rate?: number | null;
}

export interface PatientIntake {
  symptoms: string[];
  age: number;
  sex: "male" | "female" | "other";
  history?: string[];
  medications?: string[];
  vitals?: Vitals | null;
  labs?: Record<string, number> | null;
  free_text?: string;
}

export interface DiagnosisItem {
  disease_name: string;
  confidence: number;
  supporting_evidence: string[];
  graph_path: string[];
  verified_in_graph: boolean;
}

export interface EmergencyResult {
  triggered: boolean;
  pattern_name: string;
  message: string;
}

export interface GraphNode {
  id: string;
  name: string;
  type: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
}

export interface DiagnosisResponse {
  diagnoses: DiagnosisItem[];
  reasoning_summary: string;
  emergency: EmergencyResult;
  low_context: boolean;
  low_confidence: boolean;
  llm_fallback: boolean;
  treatment_advice_stripped: boolean;
  disclaimer: string;
  request_id: string;
  model_used: string;
  prompt_version: string;
  graph_nodes: GraphNode[];
  graph_edges: GraphEdge[];
}
