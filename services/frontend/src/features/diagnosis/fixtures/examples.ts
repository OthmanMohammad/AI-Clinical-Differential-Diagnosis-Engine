/**
 * Example clinical cases for quick-loading via the command palette.
 * These are curated to exercise different parts of the pipeline.
 */

import type { PatientIntake } from "@/types/api";

export interface ExampleCase {
  id: string;
  label: string;
  description: string;
  intake: PatientIntake;
}

export const EXAMPLE_CASES: ExampleCase[] = [
  {
    id: "sle",
    label: "Systemic Lupus Erythematosus",
    description: "Young woman with joint pain, fatigue, malar rash",
    intake: {
      symptoms: ["joint pain", "fatigue", "butterfly rash"],
      age: 35,
      sex: "female",
      history: ["photosensitivity"],
      medications: [],
      free_text:
        "Symmetric joint pain with malar rash for 3 weeks. Patient reports fatigue and low-grade fevers.",
    },
  },
  {
    id: "cardiac",
    label: "Cardiac emergency",
    description: "55yo male with classic MI presentation",
    intake: {
      symptoms: ["chest pain", "shortness of breath", "diaphoresis"],
      age: 55,
      sex: "male",
      history: ["hypertension", "hyperlipidemia"],
      medications: ["lisinopril", "atorvastatin"],
      free_text:
        "Crushing chest pain radiating to left arm and jaw, accompanied by cold sweat and nausea.",
    },
  },
  {
    id: "meningitis",
    label: "Suspected meningitis",
    description: "Young adult with classic triad",
    intake: {
      symptoms: ["severe headache", "neck stiffness", "fever"],
      age: 22,
      sex: "male",
      history: [],
      medications: [],
      free_text:
        "Sudden onset severe headache with photophobia, neck stiffness, and fever 39.5°C.",
    },
  },
  {
    id: "t2dm",
    label: "New-onset diabetes",
    description: "Middle-aged with classic polyuria/polydipsia",
    intake: {
      symptoms: ["frequent urination", "excessive thirst", "fatigue"],
      age: 48,
      sex: "female",
      history: ["obesity", "family history of diabetes"],
      medications: [],
      free_text:
        "Several weeks of increased thirst, frequent urination, and unexplained fatigue. No recent illness.",
    },
  },
  {
    id: "headache",
    label: "Simple headache",
    description: "Minimal input — tests low-context path",
    intake: {
      symptoms: ["headache"],
      age: 30,
      sex: "male",
    },
  },
];

export function getExampleById(id: string): ExampleCase | undefined {
  return EXAMPLE_CASES.find((c) => c.id === id);
}
