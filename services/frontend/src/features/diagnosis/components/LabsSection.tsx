import * as React from "react";
import { createPortal } from "react-dom";
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

interface DropdownPos {
  left: number;
  top?: number;
  bottom?: number;
  width: number;
  maxHeight: number;
  placement: "bottom" | "top";
}

/** Compute a viewport-relative position that auto-flips when the input is
 *  near the bottom of the viewport. Used by the portal-rendered dropdown
 *  so it can escape every parent overflow and still cling to the input. */
function computePos(el: HTMLElement): DropdownPos {
  const rect = el.getBoundingClientRect();
  const vh = window.innerHeight;
  const GAP = 4;
  const MAX = 320; // equivalent to max-h-80
  const EDGE = 8;
  const spaceBelow = vh - rect.bottom - EDGE;
  const spaceAbove = rect.top - EDGE;
  // Prefer opening downward unless there's clearly more room above.
  const openDown = spaceBelow >= 200 || spaceBelow >= spaceAbove;
  const avail = openDown ? spaceBelow : spaceAbove;
  const maxHeight = Math.max(120, Math.min(MAX, avail - GAP));
  return {
    left: rect.left,
    width: rect.width,
    top: openDown ? rect.bottom + GAP : undefined,
    bottom: openDown ? undefined : vh - rect.top + GAP,
    maxHeight,
    placement: openDown ? "bottom" : "top",
  };
}

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
  const [dropdownPos, setDropdownPos] = React.useState<DropdownPos | null>(null);

  const nameRef = React.useRef<HTMLInputElement>(null);
  const valueRef = React.useRef<HTMLInputElement>(null);
  const suggestionRefs = React.useRef<Array<HTMLLIElement | null>>([]);
  // Tracks what caused the last change to `activeSuggestion` so we only
  // auto-scroll on keyboard nav — mouse hover changes must NOT trigger
  // scrollIntoView, otherwise they fight the user's wheel scroll.
  const navSourceRef = React.useRef<"keyboard" | "mouse">("mouse");

  const filteredLabs = React.useMemo(() => {
    const q = draftKey.trim().toLowerCase();
    if (q.length === 0) return COMMON_LABS;
    return COMMON_LABS.filter((l) => l.toLowerCase().includes(q));
  }, [draftKey]);

  React.useEffect(() => {
    setActiveSuggestion(0);
    navSourceRef.current = "mouse";
  }, [draftKey]);

  React.useEffect(() => {
    // Only auto-scroll on keyboard navigation — smooth-scrolling on every
    // mouse hover fights the wheel scroll and makes the dropdown feel stuck.
    if (navSourceRef.current !== "keyboard") return;
    const el = suggestionRefs.current[activeSuggestion];
    if (el) {
      el.scrollIntoView({ block: "nearest" });
    }
  }, [activeSuggestion]);

  // ---- Portal positioning ----
  // The dropdown renders at document.body with position: fixed so it
  // escapes every parent overflow (Radix ScrollArea, workspace panel,
  // labs accordion, ...). We recompute its rect on every scroll/resize
  // so it stays glued to the input, and throttle with rAF to avoid
  // hammering React during a drag-scroll.
  React.useLayoutEffect(() => {
    if (!keyFocused) return;
    if (!nameRef.current) return;

    let rafId: number | null = null;
    const update = () => {
      if (rafId !== null) return;
      rafId = requestAnimationFrame(() => {
        rafId = null;
        if (nameRef.current) {
          setDropdownPos(computePos(nameRef.current));
        }
      });
    };

    update();
    // capture: true catches scrolls from Radix ScrollArea's inner viewport
    // and any other nested scrollable ancestors that don't bubble to window.
    window.addEventListener("scroll", update, true);
    window.addEventListener("resize", update);
    return () => {
      if (rafId !== null) cancelAnimationFrame(rafId);
      window.removeEventListener("scroll", update, true);
      window.removeEventListener("resize", update);
    };
  }, [keyFocused]);

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
      navSourceRef.current = "keyboard";
      setActiveSuggestion((i) => Math.min(i + 1, filteredLabs.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      navSourceRef.current = "keyboard";
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

  const dropdownOpen =
    keyFocused && filteredLabs.length > 0 && dropdownPos !== null;

  const dropdownNode = (
    <AnimatePresence>
      {dropdownOpen && dropdownPos && (
        <motion.div
          key="labs-dropdown"
          initial={{
            opacity: 0,
            y: dropdownPos.placement === "bottom" ? -4 : 4,
          }}
          animate={{ opacity: 1, y: 0 }}
          exit={{
            opacity: 0,
            y: dropdownPos.placement === "bottom" ? -4 : 4,
          }}
          transition={{ duration: 0.12 }}
          style={{
            position: "fixed",
            left: dropdownPos.left,
            top: dropdownPos.top,
            bottom: dropdownPos.bottom,
            width: dropdownPos.width,
            maxHeight: dropdownPos.maxHeight,
            backgroundColor: "hsl(var(--popover))",
            color: "hsl(var(--popover-foreground))",
          }}
          className="z-[60] overflow-y-auto overscroll-contain rounded-md border border-border shadow-2xl"
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
                    // preventDefault keeps the input focused so blur
                    // doesn't fire and unmount the dropdown before
                    // our click handler runs.
                    e.preventDefault();
                    setDraftKey(l);
                    setTimeout(() => valueRef.current?.focus(), 10);
                  }}
                  onMouseEnter={() => {
                    navSourceRef.current = "mouse";
                    setActiveSuggestion(i);
                  }}
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
  );

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
                <div className="flex gap-1.5">
                  <div className="flex-1">
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
                      aria-autocomplete="list"
                      aria-expanded={dropdownOpen}
                    />
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

      {typeof document !== "undefined" &&
        createPortal(dropdownNode, document.body)}
    </div>
  );
}
