/**
 * Application-wide constants.
 */

export const APP_NAME = "MooseGlove";
export const APP_TAGLINE = "AI Clinical Differential Diagnosis Engine";
export const APP_VERSION = "0.1.0";

/** localStorage keys (namespaced to avoid collisions). */
export const STORAGE_KEYS = {
  theme: "mooseglove.theme",
  intake: "mooseglove.intake",
  workspaceLayout: "mooseglove.layout",
  sidebarCollapsed: "mooseglove.sidebar.collapsed",
  graphLayoutType: "mooseglove.graph.layout",
} as const;

/** Query keys for TanStack Query. */
export const QUERY_KEYS = {
  medicalTerms: ["medical-terms"] as const,
  health: ["health"] as const,
  graphNode: (id: string) => ["graph", "node", id] as const,
};

/** Entity types recognised from the backend knowledge graph. */
export const ENTITY_TYPES = ["Disease", "Symptom", "Gene", "Drug", "Phenotype", "Anatomy"] as const;

export type EntityType = (typeof ENTITY_TYPES)[number];

/** Maps entity types to CSS variable names for consistent coloring. */
export const ENTITY_COLOR_VAR: Record<EntityType, string> = {
  Disease: "--disease",
  Symptom: "--symptom",
  Gene: "--gene",
  Drug: "--drug",
  Phenotype: "--phenotype",
  Anatomy: "--anatomy",
};

/** Display labels (lowercase user-friendly). */
export const ENTITY_LABELS: Record<EntityType, string> = {
  Disease: "disease",
  Symptom: "symptom",
  Gene: "gene",
  Drug: "drug",
  Phenotype: "phenotype",
  Anatomy: "anatomy",
};
