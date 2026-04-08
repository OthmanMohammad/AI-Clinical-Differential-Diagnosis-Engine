/** Left panel — Clinical intake form. */

import { useState, type FormEvent } from "react";
import type { PatientIntake, Vitals } from "@/types/api";

interface ClinicalFormProps {
  onSubmit: (intake: PatientIntake) => void;
  isLoading: boolean;
}

export default function ClinicalForm({ onSubmit, isLoading }: ClinicalFormProps) {
  const [symptoms, setSymptoms] = useState<string[]>([]);
  const [symptomInput, setSymptomInput] = useState("");
  const [age, setAge] = useState(40);
  const [sex, setSex] = useState<"male" | "female" | "other">("male");
  const [history, setHistory] = useState<string[]>([]);
  const [historyInput, setHistoryInput] = useState("");
  const [medications, setMedications] = useState<string[]>([]);
  const [medInput, setMedInput] = useState("");
  const [freeText, setFreeText] = useState("");
  const [showVitals, setShowVitals] = useState(false);
  const [vitals, setVitals] = useState<Vitals>({});
  const [showLabs, setShowLabs] = useState(false);
  const [labsText, setLabsText] = useState("");

  function addTag(
    value: string,
    list: string[],
    setter: (v: string[]) => void,
    inputSetter: (v: string) => void,
  ) {
    const trimmed = value.trim();
    if (trimmed && !list.includes(trimmed)) {
      setter([...list, trimmed]);
    }
    inputSetter("");
  }

  function removeTag(index: number, list: string[], setter: (v: string[]) => void) {
    setter(list.filter((_, i) => i !== index));
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (symptoms.length === 0) return;

    let parsedLabs: Record<string, number> | undefined;
    if (labsText.trim()) {
      try {
        parsedLabs = JSON.parse(labsText);
      } catch {
        parsedLabs = undefined;
      }
    }

    const intake: PatientIntake = {
      symptoms,
      age,
      sex,
      history: history.length > 0 ? history : undefined,
      medications: medications.length > 0 ? medications : undefined,
      vitals: showVitals ? vitals : undefined,
      labs: parsedLabs,
      free_text: freeText || undefined,
    };

    onSubmit(intake);
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <h2 className="text-lg font-semibold text-white">Clinical Intake</h2>

      {/* Symptoms */}
      <div>
        <label className="block text-sm text-gray-400 mb-1">
          Symptoms <span className="text-red-400">*</span>
        </label>
        <div className="flex gap-2">
          <input
            type="text"
            value={symptomInput}
            onChange={(e) => setSymptomInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addTag(symptomInput, symptoms, setSymptoms, setSymptomInput);
              }
            }}
            placeholder="Type symptom + Enter"
            className="flex-1 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
          />
        </div>
        <div className="flex flex-wrap gap-1 mt-2">
          {symptoms.map((s, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1 bg-blue-900/50 text-blue-300 text-xs px-2 py-1 rounded-full"
            >
              {s}
              <button type="button" onClick={() => removeTag(i, symptoms, setSymptoms)}>
                x
              </button>
            </span>
          ))}
        </div>
      </div>

      {/* Age + Sex */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-sm text-gray-400 mb-1">Age</label>
          <input
            type="number"
            value={age}
            onChange={(e) => setAge(Number(e.target.value))}
            min={0}
            max={130}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1">Sex</label>
          <select
            value={sex}
            onChange={(e) => setSex(e.target.value as "male" | "female" | "other")}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
          >
            <option value="male">Male</option>
            <option value="female">Female</option>
            <option value="other">Other</option>
          </select>
        </div>
      </div>

      {/* History */}
      <div>
        <label className="block text-sm text-gray-400 mb-1">Medical History</label>
        <input
          type="text"
          value={historyInput}
          onChange={(e) => setHistoryInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              addTag(historyInput, history, setHistory, setHistoryInput);
            }
          }}
          placeholder="Type condition + Enter"
          className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
        />
        <div className="flex flex-wrap gap-1 mt-2">
          {history.map((h, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1 bg-purple-900/50 text-purple-300 text-xs px-2 py-1 rounded-full"
            >
              {h}
              <button type="button" onClick={() => removeTag(i, history, setHistory)}>
                x
              </button>
            </span>
          ))}
        </div>
      </div>

      {/* Medications */}
      <div>
        <label className="block text-sm text-gray-400 mb-1">Current Medications</label>
        <input
          type="text"
          value={medInput}
          onChange={(e) => setMedInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              addTag(medInput, medications, setMedications, setMedInput);
            }
          }}
          placeholder="Type medication + Enter"
          className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
        />
        <div className="flex flex-wrap gap-1 mt-2">
          {medications.map((m, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1 bg-amber-900/50 text-amber-300 text-xs px-2 py-1 rounded-full"
            >
              {m}
              <button type="button" onClick={() => removeTag(i, medications, setMedications)}>
                x
              </button>
            </span>
          ))}
        </div>
      </div>

      {/* Vitals (collapsible) */}
      <div>
        <button
          type="button"
          onClick={() => setShowVitals(!showVitals)}
          className="text-sm text-gray-400 hover:text-white"
        >
          {showVitals ? "- Hide Vitals" : "+ Add Vitals"}
        </button>
        {showVitals && (
          <div className="grid grid-cols-2 gap-2 mt-2">
            {[
              { key: "temperature_c", label: "Temp (C)", min: 30, max: 45, step: 0.1 },
              { key: "heart_rate", label: "HR (bpm)", min: 20, max: 300, step: 1 },
              { key: "systolic_bp", label: "SBP (mmHg)", min: 50, max: 300, step: 1 },
              { key: "diastolic_bp", label: "DBP (mmHg)", min: 20, max: 200, step: 1 },
              { key: "spo2", label: "SpO2 (%)", min: 50, max: 100, step: 0.1 },
              { key: "respiratory_rate", label: "RR (/min)", min: 4, max: 60, step: 1 },
            ].map(({ key, label, min, max, step }) => (
              <div key={key}>
                <label className="block text-xs text-gray-500">{label}</label>
                <input
                  type="number"
                  min={min}
                  max={max}
                  step={step}
                  value={(vitals as Record<string, number | undefined>)[key] ?? ""}
                  onChange={(e) =>
                    setVitals({
                      ...vitals,
                      [key]: e.target.value ? Number(e.target.value) : undefined,
                    })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-white focus:outline-none focus:border-blue-500"
                />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Labs (collapsible) */}
      <div>
        <button
          type="button"
          onClick={() => setShowLabs(!showLabs)}
          className="text-sm text-gray-400 hover:text-white"
        >
          {showLabs ? "- Hide Labs" : "+ Add Labs"}
        </button>
        {showLabs && (
          <textarea
            value={labsText}
            onChange={(e) => setLabsText(e.target.value)}
            placeholder='{"WBC": 12.5, "Hemoglobin": 10.2}'
            rows={3}
            className="w-full mt-2 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 font-mono"
          />
        )}
      </div>

      {/* Free text */}
      <div>
        <label className="block text-sm text-gray-400 mb-1">Additional Notes</label>
        <textarea
          value={freeText}
          onChange={(e) => setFreeText(e.target.value)}
          placeholder="Free text clinical description..."
          rows={3}
          maxLength={2000}
          className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
        />
        <div className="text-xs text-gray-600 text-right">{freeText.length}/2000</div>
      </div>

      {/* Submit */}
      <button
        type="submit"
        disabled={isLoading || symptoms.length === 0}
        className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:text-gray-500 text-white font-medium py-2.5 rounded transition-colors"
      >
        {isLoading ? "Analyzing..." : "Generate Differential Diagnosis"}
      </button>
    </form>
  );
}
