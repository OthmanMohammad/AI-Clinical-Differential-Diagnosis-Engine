/**
 * Human-friendly labels and colors for PrimeKG edge types.
 */

export const EDGE_TYPE_LABEL: Record<string, string> = {
  disease_disease: "related to",
  disease_protein: "associated protein",
  drug_protein: "targets",
  drug_disease: "treats",
  disease_phenotype_positive: "presents with",
  disease_phenotype_negative: "absent in",
  phenotype_phenotype: "co-occurs with",
  exposure_disease: "exposure",
};

export function formatEdgeLabel(type: string): string {
  return EDGE_TYPE_LABEL[type] ?? type.replace(/_/g, " ");
}
