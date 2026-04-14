import * as React from "react";
import { ChevronDown, FlaskConical, Plus, X } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { useIntakeStore } from "@/features/diagnosis/store/intake";

const COMMON_LABS = [
  "WBC",
  "Hemoglobin",
  "Platelets",
  "Glucose",
  "Creatinine",
  "BUN",
  "Sodium",
  "Potassium",
  "ALT",
  "AST",
  "CRP",
  "ESR",
];

export function LabsSection() {
  const labs = useIntakeStore((s) => s.labs);
  const addLab = useIntakeStore((s) => s.addLab);
  const removeLab = useIntakeStore((s) => s.removeLab);
  const expanded = useIntakeStore((s) => s.labsExpanded);
  const setField = useIntakeStore((s) => s.setField);

  const [draftKey, setDraftKey] = React.useState("");
  const [draftValue, setDraftValue] = React.useState("");

  const commit = () => {
    const key = draftKey.trim();
    const value = Number(draftValue);
    if (!key || Number.isNaN(value)) return;
    addLab(key, value);
    setDraftKey("");
    setDraftValue("");
  };

  return (
    <div className="rounded-md border border-border">
      <button
        type="button"
        className={cn(
          "flex w-full items-center justify-between rounded-md px-3 py-2 text-sm font-medium transition-colors hover:bg-accent/50",
          expanded && "bg-accent/30",
        )}
        onClick={() => setField("labsExpanded", !expanded)}
        aria-expanded={expanded}
      >
        <span className="flex items-center gap-2">
          <FlaskConical className="h-3.5 w-3.5 text-[hsl(var(--gene))]" />
          Labs
          {labs.length > 0 && (
            <span className="text-[10px] text-muted-foreground">({labs.length} set)</span>
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
            <div className="space-y-2 border-t border-border p-3">
              {labs.length > 0 && (
                <ul className="space-y-1">
                  {labs.map((lab, i) => (
                    <li
                      key={`${lab.key}-${i}`}
                      className="flex items-center justify-between rounded-sm bg-muted/30 px-2 py-1 text-xs"
                    >
                      <span className="font-mono">{lab.key}</span>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-foreground/80">{lab.value}</span>
                        <button
                          type="button"
                          onClick={() => removeLab(i)}
                          aria-label={`Remove ${lab.key}`}
                          className="text-muted-foreground hover:text-foreground"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}

              <div className="space-y-1.5">
                <Label className="text-[10px]">Add lab</Label>
                <div className="flex gap-1.5">
                  <Input
                    list="lab-suggestions"
                    value={draftKey}
                    onChange={(e) => setDraftKey(e.target.value)}
                    placeholder="Name"
                    className="h-8 flex-1 text-xs"
                    onKeyDown={(e) => e.key === "Enter" && commit()}
                  />
                  <datalist id="lab-suggestions">
                    {COMMON_LABS.map((l) => (
                      <option key={l} value={l} />
                    ))}
                  </datalist>
                  <Input
                    type="number"
                    step="any"
                    value={draftValue}
                    onChange={(e) => setDraftValue(e.target.value)}
                    placeholder="Value"
                    className="h-8 w-20 text-xs"
                    onKeyDown={(e) => e.key === "Enter" && commit()}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="icon-sm"
                    onClick={commit}
                    aria-label="Add lab"
                  >
                    <Plus className="h-3 w-3" />
                  </Button>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
