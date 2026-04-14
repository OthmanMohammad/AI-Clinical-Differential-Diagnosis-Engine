import { ChevronDown, Heart } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { useIntakeStore } from "@/features/diagnosis/store/intake";
import type { Vitals } from "@/types/api";

interface VitalField {
  key: keyof Vitals;
  label: string;
  unit: string;
  min: number;
  max: number;
  step: number;
}

const FIELDS: VitalField[] = [
  { key: "temperature_c", label: "Temperature", unit: "°C", min: 30, max: 45, step: 0.1 },
  { key: "heart_rate", label: "Heart rate", unit: "bpm", min: 20, max: 300, step: 1 },
  { key: "systolic_bp", label: "Systolic BP", unit: "mmHg", min: 50, max: 300, step: 1 },
  { key: "diastolic_bp", label: "Diastolic BP", unit: "mmHg", min: 20, max: 200, step: 1 },
  { key: "spo2", label: "SpO₂", unit: "%", min: 50, max: 100, step: 0.1 },
  { key: "respiratory_rate", label: "Resp. rate", unit: "/min", min: 4, max: 60, step: 1 },
];

export function VitalsSection() {
  const vitals = useIntakeStore((s) => s.vitals);
  const setVital = useIntakeStore((s) => s.setVital);
  const expanded = useIntakeStore((s) => s.vitalsExpanded);
  const setField = useIntakeStore((s) => s.setField);

  return (
    <div className="rounded-md border border-border">
      <button
        type="button"
        className={cn(
          "flex w-full items-center justify-between rounded-md px-3 py-2 text-sm font-medium transition-colors hover:bg-accent/50",
          expanded && "bg-accent/30",
        )}
        onClick={() => setField("vitalsExpanded", !expanded)}
        aria-expanded={expanded}
      >
        <span className="flex items-center gap-2">
          <Heart className="h-3.5 w-3.5 text-[hsl(var(--drug))]" />
          Vital signs
          {Object.values(vitals).some((v) => v != null) && (
            <span className="text-[10px] text-muted-foreground">
              ({Object.values(vitals).filter((v) => v != null).length} set)
            </span>
          )}
        </span>
        <ChevronDown
          className={cn("h-4 w-4 transition-transform", expanded && "rotate-180")}
        />
      </button>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden"
          >
            <div className="grid grid-cols-2 gap-3 border-t border-border p-3">
              {FIELDS.map((f) => (
                <div key={f.key} className="space-y-1">
                  <Label className="text-[10px]">
                    {f.label} <span className="font-mono opacity-60">{f.unit}</span>
                  </Label>
                  <Input
                    type="number"
                    inputMode="decimal"
                    min={f.min}
                    max={f.max}
                    step={f.step}
                    value={vitals[f.key] ?? ""}
                    onChange={(e) =>
                      setVital(
                        f.key,
                        e.target.value === ""
                          ? null
                          : Number(e.target.value),
                      )
                    }
                    className="h-8 text-sm"
                    aria-label={f.label}
                  />
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
