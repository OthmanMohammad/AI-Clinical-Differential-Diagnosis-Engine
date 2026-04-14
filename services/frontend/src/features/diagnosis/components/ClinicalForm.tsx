/**
 * Clinical intake form — the left panel of the workspace.
 *
 * Wires the Zustand intake store to visual inputs, validates via Zod, and
 * submits to the diagnosis hook. All state lives in the store so navigating
 * away / refreshing doesn't lose work.
 */

import * as React from "react";
import { useHotkeys } from "react-hotkeys-hook";
import { Loader2, Send, Sparkles } from "lucide-react";
import { motion } from "framer-motion";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Kbd } from "@/components/ui/kbd";
import { useIntakeStore } from "@/features/diagnosis/store/intake";
import { AgeInput } from "@/features/diagnosis/components/AgeInput";
import { TagInput } from "@/features/diagnosis/components/TagInput";
import { VitalsSection } from "@/features/diagnosis/components/VitalsSection";
import { LabsSection } from "@/features/diagnosis/components/LabsSection";
import { useMedicalTerms } from "@/features/diagnosis/hooks/useMedicalTerms";
import { patientIntakeSchema } from "@/features/diagnosis/schemas/intake.schema";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

interface ClinicalFormProps {
  isSubmitting: boolean;
  onSubmit: () => void;
}

export function ClinicalForm({ isSubmitting, onSubmit }: ClinicalFormProps) {
  const symptoms = useIntakeStore((s) => s.symptoms);
  const age = useIntakeStore((s) => s.age);
  const sex = useIntakeStore((s) => s.sex);
  const history = useIntakeStore((s) => s.history);
  const medications = useIntakeStore((s) => s.medications);
  const freeText = useIntakeStore((s) => s.freeText);

  const addSymptom = useIntakeStore((s) => s.addSymptom);
  const removeSymptom = useIntakeStore((s) => s.removeSymptom);
  const addHistory = useIntakeStore((s) => s.addHistory);
  const removeHistory = useIntakeStore((s) => s.removeHistory);
  const addMedication = useIntakeStore((s) => s.addMedication);
  const removeMedication = useIntakeStore((s) => s.removeMedication);
  const setField = useIntakeStore((s) => s.setField);
  const toPayload = useIntakeStore((s) => s.toPayload);

  const { data: medicalTerms = [] } = useMedicalTerms();
  const symptomInputRef = React.useRef<HTMLInputElement>(null);

  const handleSubmit = React.useCallback(() => {
    const parsed = patientIntakeSchema.safeParse(toPayload());
    if (!parsed.success) {
      const first = parsed.error.errors[0];
      toast.error(first?.message ?? "Form validation failed");
      return;
    }
    onSubmit();
  }, [toPayload, onSubmit]);

  useHotkeys(
    "mod+enter",
    (e) => {
      e.preventDefault();
      if (!isSubmitting) handleSubmit();
    },
    { enableOnFormTags: true },
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-h3 font-semibold tracking-tight">Clinical intake</h2>
          <p className="text-xs text-muted-foreground">
            Describe the presentation
          </p>
        </div>
        <div className="rounded-md bg-primary/10 px-2 py-1 text-[10px] font-medium uppercase tracking-wider text-primary">
          <Sparkles className="mr-1 inline h-2.5 w-2.5" />
          Graph RAG
        </div>
      </div>

      {/* Scrollable body */}
      <ScrollArea className="-mr-2 flex-1 pr-2">
        <div className="space-y-4 px-0.5 pb-4">
          {/* Symptoms */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="symptoms">
                Symptoms <span className="text-destructive">*</span>
              </Label>
            </div>
            <TagInput
              value={symptoms}
              onAdd={addSymptom}
              onRemove={removeSymptom}
              suggestions={medicalTerms}
              placeholder="Type a symptom and press Enter…"
              inputRef={symptomInputRef}
              accentClass="bg-primary/10 text-primary border-primary/25"
              aria-label="Symptoms"
            />
          </div>

          {/* Age + Sex */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="age">Age</Label>
              <AgeInput
                id="age"
                value={age}
                onChange={(n) => setField("age", n)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="sex">Sex</Label>
              <Select
                value={sex}
                onValueChange={(v) => setField("sex", v as typeof sex)}
              >
                <SelectTrigger id="sex" className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="male">Male</SelectItem>
                  <SelectItem value="female">Female</SelectItem>
                  <SelectItem value="other">Other</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* History */}
          <div className="space-y-1.5">
            <Label>Medical history</Label>
            <TagInput
              value={history}
              onAdd={addHistory}
              onRemove={removeHistory}
              suggestions={medicalTerms}
              placeholder="Past conditions…"
              accentClass="bg-[hsl(var(--disease))]/10 text-[hsl(var(--disease))] border-[hsl(var(--disease))]/25"
              aria-label="Medical history"
            />
          </div>

          {/* Medications */}
          <div className="space-y-1.5">
            <Label>Medications</Label>
            <TagInput
              value={medications}
              onAdd={addMedication}
              onRemove={removeMedication}
              placeholder="Current medications…"
              accentClass="bg-[hsl(var(--drug))]/10 text-[hsl(var(--drug))] border-[hsl(var(--drug))]/25"
              aria-label="Medications"
            />
          </div>

          {/* Vitals */}
          <VitalsSection />

          {/* Labs */}
          <LabsSection />

          {/* Free text */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label>Clinical notes</Label>
              <span className="font-mono text-[10px] text-muted-foreground">
                {freeText.length}/2000
              </span>
            </div>
            <Textarea
              value={freeText}
              onChange={(e) => setField("freeText", e.target.value)}
              placeholder="Free-text description. Negations like 'no chest pain' are handled."
              maxLength={2000}
              rows={4}
              className="text-xs"
            />
          </div>
        </div>
      </ScrollArea>

      {/* Submit footer */}
      <div className="mt-3 border-t border-border pt-3">
        <Button
          type="button"
          className="group w-full gap-2"
          disabled={isSubmitting || symptoms.length === 0}
          onClick={handleSubmit}
        >
          {isSubmitting ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Analyzing…
            </>
          ) : (
            <motion.span
              initial={false}
              className="flex items-center gap-2"
              whileHover={{ x: 2 }}
              transition={{ duration: 0.2 }}
            >
              Generate differential
              <Send className={cn("h-3.5 w-3.5 transition-transform")} />
              <Kbd className="ml-1 bg-primary-foreground/10 text-primary-foreground/80">
                Ctrl ↵
              </Kbd>
            </motion.span>
          )}
        </Button>
      </div>
    </div>
  );
}
