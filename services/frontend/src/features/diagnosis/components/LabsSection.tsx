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
  "HbA1c",
  "Creatinine",
  "BUN",
  "Sodium",
  "Potassium",
  "Chloride",
  "Bicarbonate",
  "Calcium",
  "Magnesium",
  "ALT",
  "AST",
  "Alkaline Phosphatase",
  "Total Bilirubin",
  "Albumin",
  "CRP",
  "ESR",
  "Troponin",
  "BNP",
  "TSH",
  "Lactate",
  "INR",
];

export function LabsSection() {
  const labs = useIntakeStore((s) => s.labs);
  const addLab = useIntakeStore((s) => s.addLab);
  const removeLab = useIntakeStore((s) => s.removeLab);
  const expanded = useIntakeStore((s) => s.labsExpanded);
  const setField = useIntakeStore((s) => s.setField);

  const [draftKey, setDraftKey] = React.useState("");
  const [draftValue, setDraftValue] = React.useState("");
  const [keyFocused, setKeyFocused] = React.useState(false);
  const [activeSuggestion, setActiveSuggestion] = React.useState(0);

  const nameRef = React.useRef<HTMLInputElement>(null);
  const valueRef = React.useRef<HTMLInputElement>(null);
  const suggestionRefs = React.useRef<Array<HTMLLIElement | null>>([]);

  const filteredLabs = React.useMemo(() => {
    const q = draftKey.trim().toLowerCase();
    if (q.length === 0) return COMMON_LABS;
    return COMMON_LABS.filter((l) => l.toLowerCase().includes(q));
  }, [draftKey]);

  React.useEffect(() => {
    setActiveSuggestion(0);
  }, [draftKey]);

  React.useEffect(() => {
    const el = suggestionRefs.current[activeSuggestion];
    if (el) {
      el.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [activeSuggestion]);

  const commit = () => {
    const key = draftKey.trim();
    const value = Number(draftValue);
    if (!key || draftValue === "" || Number.isNaN(value)) return;
    addLab(key, value);
    setDraftKey("");
    setDraftValue("");
    // After committing, refocus the name field for the next lab entry
    setTimeout(() => nameRef.current?.focus(), 10);
  };

  const handleNameKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === "Tab") {
      e.preventDefault();
      // If the user has highlighted a suggestion, accept it
      if (filteredLabs[activeSuggestion]) {
        setDraftKey(filteredLabs[activeSuggestion]);
      }
      // Then advance to the value field
      setTimeout(() => valueRef.current?.focus(), 10);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveSuggestion((i) => Math.min(i + 1, filteredLabs.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveSuggestion((i) => Math.max(i - 1, 0));
    } else if (e.key === "Escape") {
      setDraftKey("");
    }
  };

  const handleValueKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      commit();
    } else if (e.key === "Escape") {
      setDraftValue("");
    }
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
                <Label className="text-[10px]">Add lab test</Label>
                <div className="relative flex gap-1.5">
                  <div className="relative flex-1">
                    <Input
                      ref={nameRef}
                      value={draftKey}
                      onChange={(e) => setDraftKey(e.target.value)}
                      onFocus={() => setKeyFocused(true)}
                      onBlur={() => setTimeout(() => setKeyFocused(false), 120)}
                      onKeyDown={handleNameKeyDown}
                      placeholder="Lab test"
                      className="h-8 text-xs"
                      autoComplete="off"
                    />
                    <AnimatePresence>
                      {keyFocused && filteredLabs.length > 0 && (
                        <motion.div
                          initial={{ opacity: 0, y: -4 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, y: -4 }}
                          transition={{ duration: 0.12 }}
                          style={{
                            backgroundColor: "hsl(var(--popover))",
                            color: "hsl(var(--popover-foreground))",
                          }}
                          className="absolute left-0 right-0 top-full z-30 mt-1 max-h-48 overflow-y-auto rounded-md border border-border shadow-2xl"
                        >
                          <ul role="listbox" className="py-1">
                            {filteredLabs.map((l, i) => {
                              const isActive = i === activeSuggestion;
                              return (
                                <li
                                  key={l}
                                  ref={(el) => {
                                    suggestionRefs.current[i] = el;
                                  }}
                                  role="option"
                                  aria-selected={isActive}
                                  onMouseDown={(e) => {
                                    e.preventDefault();
                                    setDraftKey(l);
                                    setTimeout(() => valueRef.current?.focus(), 10);
                                  }}
                                  onMouseEnter={() => setActiveSuggestion(i)}
                                  style={
                                    isActive
                                      ? {
                                          backgroundColor: "hsl(var(--primary))",
                                          color: "hsl(var(--primary-foreground))",
                                        }
                                      : undefined
                                  }
                                  className="cursor-pointer px-3 py-1 text-xs font-medium transition-colors hover:bg-muted/60"
                                >
                                  {l}
                                </li>
                              );
                            })}
                          </ul>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                  <Input
                    ref={valueRef}
                    type="number"
                    step="any"
                    value={draftValue}
                    onChange={(e) => setDraftValue(e.target.value)}
                    placeholder="Value"
                    className="h-8 w-20 text-xs"
                    onKeyDown={handleValueKeyDown}
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
