/** Hook for submitting diagnosis requests via TanStack Query. */

import { useMutation } from "@tanstack/react-query";
import { submitDiagnosis, ApiError } from "@/lib/api";
import type { PatientIntake, DiagnosisResponse } from "@/types/api";

export function useDiagnosis() {
  return useMutation<DiagnosisResponse, ApiError, PatientIntake>({
    mutationFn: submitDiagnosis,
  });
}
