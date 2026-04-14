/**
 * Zod schemas mirroring the backend Pydantic models.
 * Used for client-side validation on the intake form.
 */

import { z } from "zod";

export const sexSchema = z.enum(["male", "female", "other"]);

export const vitalsSchema = z.object({
  temperature_c: z.number().min(30).max(45).nullable().optional(),
  heart_rate: z.number().int().min(20).max(300).nullable().optional(),
  systolic_bp: z.number().int().min(50).max(300).nullable().optional(),
  diastolic_bp: z.number().int().min(20).max(200).nullable().optional(),
  spo2: z.number().min(50).max(100).nullable().optional(),
  respiratory_rate: z.number().int().min(4).max(60).nullable().optional(),
});

export const patientIntakeSchema = z.object({
  symptoms: z.array(z.string().min(1)).min(1, "Add at least one symptom").max(20),
  age: z.number().int().min(0).max(130),
  sex: sexSchema,
  history: z.array(z.string().min(1)).max(10).optional(),
  medications: z.array(z.string().min(1)).max(20).optional(),
  vitals: vitalsSchema.nullable().optional(),
  labs: z.record(z.string(), z.number()).nullable().optional(),
  free_text: z.string().max(2000).optional(),
});

export type PatientIntakeValidated = z.infer<typeof patientIntakeSchema>;
