/**
 * Intake form state — the current patient case being composed.
 *
 * Persisted to localStorage so a refresh doesn't lose in-progress input.
 * Keep this intentionally minimal: form field values only, nothing derived.
 */

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { STORAGE_KEYS } from "@/lib/constants";
import type { PatientIntake, Sex, Vitals } from "@/types/api";

export interface IntakeFormState {
  symptoms: string[];
  age: number;
  sex: Sex;
  history: string[];
  medications: string[];
  vitals: Vitals;
  labs: Array<{ key: string; value: number }>;
  freeText: string;
  vitalsExpanded: boolean;
  labsExpanded: boolean;
}

interface IntakeStore extends IntakeFormState {
  setField: <K extends keyof IntakeFormState>(key: K, value: IntakeFormState[K]) => void;
  addSymptom: (symptom: string) => void;
  removeSymptom: (index: number) => void;
  addHistory: (item: string) => void;
  removeHistory: (index: number) => void;
  addMedication: (item: string) => void;
  removeMedication: (index: number) => void;
  setVital: <K extends keyof Vitals>(key: K, value: Vitals[K]) => void;
  addLab: (key: string, value: number) => void;
  removeLab: (index: number) => void;
  loadIntake: (intake: PatientIntake) => void;
  reset: () => void;
  /** Build a clean PatientIntake payload for the API. */
  toPayload: () => PatientIntake;
}

const INITIAL: IntakeFormState = {
  symptoms: [],
  age: 40,
  sex: "male",
  history: [],
  medications: [],
  vitals: {},
  labs: [],
  freeText: "",
  vitalsExpanded: false,
  labsExpanded: false,
};

export const useIntakeStore = create<IntakeStore>()(
  persist(
    (set, get) => ({
      ...INITIAL,

      setField: (key, value) => set({ [key]: value } as Partial<IntakeStore>),

      addSymptom: (symptom) => {
        const trimmed = symptom.trim();
        if (!trimmed) return;
        set((state) =>
          state.symptoms.includes(trimmed) ? state : { symptoms: [...state.symptoms, trimmed] },
        );
      },
      removeSymptom: (index) =>
        set((state) => ({
          symptoms: state.symptoms.filter((_, i) => i !== index),
        })),

      addHistory: (item) => {
        const trimmed = item.trim();
        if (!trimmed) return;
        set((state) =>
          state.history.includes(trimmed) ? state : { history: [...state.history, trimmed] },
        );
      },
      removeHistory: (index) =>
        set((state) => ({
          history: state.history.filter((_, i) => i !== index),
        })),

      addMedication: (item) => {
        const trimmed = item.trim();
        if (!trimmed) return;
        set((state) =>
          state.medications.includes(trimmed)
            ? state
            : { medications: [...state.medications, trimmed] },
        );
      },
      removeMedication: (index) =>
        set((state) => ({
          medications: state.medications.filter((_, i) => i !== index),
        })),

      setVital: (key, value) => set((state) => ({ vitals: { ...state.vitals, [key]: value } })),

      addLab: (key, value) => {
        const trimmed = key.trim();
        if (!trimmed) return;
        set((state) => ({ labs: [...state.labs, { key: trimmed, value }] }));
      },
      removeLab: (index) => set((state) => ({ labs: state.labs.filter((_, i) => i !== index) })),

      loadIntake: (intake) =>
        set({
          symptoms: intake.symptoms ?? [],
          age: intake.age,
          sex: intake.sex,
          history: intake.history ?? [],
          medications: intake.medications ?? [],
          vitals: intake.vitals ?? {},
          labs: intake.labs
            ? Object.entries(intake.labs).map(([key, value]) => ({ key, value }))
            : [],
          freeText: intake.free_text ?? "",
          vitalsExpanded: !!intake.vitals && Object.keys(intake.vitals).length > 0,
          labsExpanded: !!intake.labs && Object.keys(intake.labs).length > 0,
        }),

      reset: () => set(INITIAL),

      toPayload: () => {
        const s = get();
        const labs = s.labs.length
          ? Object.fromEntries(s.labs.map(({ key, value }) => [key, value]))
          : null;
        const vitals = Object.values(s.vitals).some((v) => v !== undefined && v !== null)
          ? s.vitals
          : null;
        return {
          symptoms: s.symptoms,
          age: s.age,
          sex: s.sex,
          history: s.history.length ? s.history : undefined,
          medications: s.medications.length ? s.medications : undefined,
          vitals,
          labs,
          free_text: s.freeText || undefined,
        };
      },
    }),
    {
      name: STORAGE_KEYS.intake,
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        symptoms: state.symptoms,
        age: state.age,
        sex: state.sex,
        history: state.history,
        medications: state.medications,
        vitals: state.vitals,
        labs: state.labs,
        freeText: state.freeText,
        vitalsExpanded: state.vitalsExpanded,
        labsExpanded: state.labsExpanded,
      }),
    },
  ),
);
