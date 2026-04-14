/**
 * Generic chip/tag input used for symptoms, history, and medications.
 *
 * Features:
 *   - Enter or Comma to add
 *   - Backspace on empty input removes last tag
 *   - Optional autocomplete suggestions from a term set
 *   - Fully keyboard navigable
 */

import * as React from "react";
import { X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

interface TagInputProps {
  value: string[];
  onAdd: (value: string) => void;
  onRemove: (index: number) => void;
  placeholder?: string;
  suggestions?: string[];
  maxSuggestions?: number;
  inputRef?: React.Ref<HTMLInputElement>;
  accentClass?: string;
  "aria-label"?: string;
}

export function TagInput({
  value,
  onAdd,
  onRemove,
  placeholder = "Type and press Enter",
  suggestions = [],
  maxSuggestions = 8,
  inputRef,
  accentClass = "bg-primary/10 text-primary border-primary/25",
  "aria-label": ariaLabel,
}: TagInputProps) {
  const [draft, setDraft] = React.useState("");
  const [focused, setFocused] = React.useState(false);
  const [activeSuggestion, setActiveSuggestion] = React.useState(0);

  const filteredSuggestions = React.useMemo(() => {
    const q = draft.trim().toLowerCase();
    if (q.length < 2 || suggestions.length === 0) return [];
    const existing = new Set(value.map((v) => v.toLowerCase()));
    const exact: string[] = [];
    const startsWith: string[] = [];
    const contains: string[] = [];
    for (const term of suggestions) {
      const t = term.toLowerCase();
      if (existing.has(t)) continue;
      if (t === q) exact.push(term);
      else if (t.startsWith(q)) startsWith.push(term);
      else if (t.includes(q)) contains.push(term);
      if (exact.length + startsWith.length + contains.length >= maxSuggestions * 2) {
        break;
      }
    }
    return [...exact, ...startsWith, ...contains].slice(0, maxSuggestions);
  }, [draft, suggestions, value, maxSuggestions]);

  React.useEffect(() => {
    setActiveSuggestion(0);
  }, [draft]);

  const commit = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    onAdd(trimmed);
    setDraft("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      if (filteredSuggestions.length > 0 && filteredSuggestions[activeSuggestion]) {
        commit(filteredSuggestions[activeSuggestion]);
      } else {
        commit(draft);
      }
    } else if (e.key === "ArrowDown" && filteredSuggestions.length > 0) {
      e.preventDefault();
      setActiveSuggestion((i) => Math.min(i + 1, filteredSuggestions.length - 1));
    } else if (e.key === "ArrowUp" && filteredSuggestions.length > 0) {
      e.preventDefault();
      setActiveSuggestion((i) => Math.max(i - 1, 0));
    } else if (e.key === "Backspace" && draft === "" && value.length > 0) {
      onRemove(value.length - 1);
    } else if (e.key === "Escape") {
      setDraft("");
    }
  };

  return (
    <div className="relative">
      <div
        className={cn(
          "flex min-h-9 w-full flex-wrap items-center gap-1 rounded-md border border-input bg-transparent px-2 py-1.5 text-sm shadow-sm",
          "transition-colors",
          focused && "border-ring ring-1 ring-ring/30",
        )}
      >
        <AnimatePresence initial={false}>
          {value.map((tag, idx) => (
            <motion.span
              key={`${tag}-${idx}`}
              layout
              initial={{ opacity: 0, scale: 0.85 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.85 }}
              transition={{ duration: 0.15, ease: "easeOut" }}
              className={cn(
                "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium",
                accentClass,
              )}
            >
              <span>{tag}</span>
              <button
                type="button"
                className="rounded-sm opacity-70 transition-opacity hover:opacity-100 focus:outline-none focus:ring-1 focus:ring-ring"
                onClick={() => onRemove(idx)}
                aria-label={`Remove ${tag}`}
              >
                <X className="h-3 w-3" />
              </button>
            </motion.span>
          ))}
        </AnimatePresence>
        <Input
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => setFocused(true)}
          onBlur={() => setTimeout(() => setFocused(false), 120)}
          placeholder={value.length === 0 ? placeholder : ""}
          aria-label={ariaLabel ?? placeholder}
          className="h-6 flex-1 border-0 bg-transparent p-0 shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
        />
      </div>

      <AnimatePresence>
        {focused && filteredSuggestions.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.12 }}
            style={{
              backgroundColor: "hsl(var(--popover))",
              color: "hsl(var(--popover-foreground))",
            }}
            className="absolute left-0 right-0 top-full z-30 mt-1 overflow-hidden rounded-md border border-border shadow-2xl"
          >
            <ul role="listbox" className="max-h-64 overflow-y-auto py-1">
              {filteredSuggestions.map((s, i) => (
                <li
                  key={s}
                  role="option"
                  aria-selected={i === activeSuggestion}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    commit(s);
                  }}
                  onMouseEnter={() => setActiveSuggestion(i)}
                  className={cn(
                    "cursor-pointer px-3 py-1.5 text-sm transition-colors",
                    i === activeSuggestion
                      ? "bg-accent text-accent-foreground"
                      : "text-foreground",
                  )}
                >
                  {s}
                </li>
              ))}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
