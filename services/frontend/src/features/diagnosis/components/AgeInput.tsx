import * as React from "react";
import { Input } from "@/components/ui/input";

interface AgeInputProps {
  value: number;
  onChange: (next: number) => void;
  min?: number;
  max?: number;
  id?: string;
}

/**
 * Number input that allows transient empty values during editing.
 *
 * The native <input type="number"> with a controlled `value={age}` prop
 * causes painful UX: deleting "40" with backspace immediately re-renders
 * with value=0 because Number("") === 0, leaving the cursor in the wrong
 * place. We solve this by keeping a local string draft that's allowed
 * to be empty, and only pushing to the parent when it parses cleanly.
 */
export function AgeInput({ value, onChange, min = 0, max = 130, id }: AgeInputProps) {
  const [draft, setDraft] = React.useState<string>(() => String(value));

  // Sync down when the canonical value changes externally (e.g. example case loaded).
  React.useEffect(() => {
    if (Number(draft) !== value) {
      setDraft(String(value));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return (
    <Input
      id={id}
      type="number"
      inputMode="numeric"
      min={min}
      max={max}
      value={draft}
      onChange={(e) => {
        const next = e.target.value;
        setDraft(next);
        // Only push a valid number to the parent. Empty/invalid drafts
        // are kept locally without polluting the form state.
        if (next === "") return;
        const n = Number(next);
        if (!Number.isNaN(n) && n >= min && n <= max) {
          onChange(n);
        }
      }}
      onBlur={() => {
        // On blur, snap back to a valid value if the draft is empty/garbage.
        if (draft === "" || Number.isNaN(Number(draft))) {
          setDraft(String(value));
        }
      }}
      className="h-9"
    />
  );
}
