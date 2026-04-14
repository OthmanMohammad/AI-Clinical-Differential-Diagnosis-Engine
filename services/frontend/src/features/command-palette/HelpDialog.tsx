/**
 * Keyboard shortcuts reference dialog.
 */

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Kbd } from "@/components/ui/kbd";
import { Separator } from "@/components/ui/separator";
import { useWorkspaceStore } from "@/features/diagnosis/store/workspace";

interface Shortcut {
  keys: string[];
  description: string;
}

interface ShortcutGroup {
  title: string;
  shortcuts: Shortcut[];
}

const SHORTCUT_GROUPS: ShortcutGroup[] = [
  {
    title: "General",
    shortcuts: [
      { keys: ["Ctrl", "K"], description: "Open command palette" },
      { keys: ["?"], description: "Show this help" },
      { keys: ["Esc"], description: "Close dialog / exit fullscreen" },
    ],
  },
  {
    title: "Diagnosis",
    shortcuts: [
      { keys: ["Ctrl", "Enter"], description: "Submit diagnosis" },
      { keys: ["Ctrl", "/"], description: "Focus symptom input" },
      { keys: ["Ctrl", "N"], description: "New diagnosis (clear form)" },
    ],
  },
  {
    title: "Graph",
    shortcuts: [
      { keys: ["F"], description: "Toggle fullscreen graph" },
      { keys: ["Ctrl", "F"], description: "Search graph nodes" },
      { keys: ["+"], description: "Zoom in" },
      { keys: ["-"], description: "Zoom out" },
      { keys: ["0"], description: "Reset zoom / fit to screen" },
    ],
  },
  {
    title: "Appearance",
    shortcuts: [{ keys: ["Ctrl", "Shift", "T"], description: "Toggle theme" }],
  },
];

export function HelpDialog() {
  const open = useWorkspaceStore((s) => s.helpOpen);
  const setOpen = useWorkspaceStore((s) => s.setHelpOpen);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Keyboard shortcuts</DialogTitle>
          <DialogDescription>
            Navigate PathoDX without ever reaching for your mouse.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {SHORTCUT_GROUPS.map((group, idx) => (
            <div key={group.title}>
              {idx > 0 && <Separator className="my-3" />}
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {group.title}
              </h4>
              <div className="space-y-2">
                {group.shortcuts.map((s) => (
                  <div
                    key={s.description}
                    className="flex items-center justify-between"
                  >
                    <span className="text-sm text-foreground">{s.description}</span>
                    <div className="flex items-center gap-1">
                      {s.keys.map((k, i) => (
                        <span key={`${s.description}-${k}-${i}`} className="inline-flex items-center gap-1">
                          <Kbd>{k}</Kbd>
                          {i < s.keys.length - 1 && (
                            <span className="text-xs text-muted-foreground">+</span>
                          )}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
