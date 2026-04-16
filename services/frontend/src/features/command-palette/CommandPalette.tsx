/**
 * Global command palette — Cmd+K to open.
 *
 * Commands are organised into groups. Each command has an icon, label,
 * optional keyboard shortcut, and an action. Actions close the palette
 * automatically via `run`.
 */

import * as React from "react";
import {
  Beaker,
  FileText,
  HelpCircle,
  Maximize2,
  Moon,
  Plus,
  RotateCcw,
  Stethoscope,
  Sun,
} from "lucide-react";
import { toast } from "sonner";

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from "@/components/ui/command";
import { useTheme } from "@/hooks/useTheme";
import { useWorkspaceStore } from "@/features/diagnosis/store/workspace";
import { useIntakeStore } from "@/features/diagnosis/store/intake";
import { EXAMPLE_CASES } from "@/features/diagnosis/fixtures/examples";
import { logger } from "@/lib/logger";

export function CommandPalette() {
  const open = useWorkspaceStore((s) => s.commandPaletteOpen);
  const setOpen = useWorkspaceStore((s) => s.setCommandPaletteOpen);
  const toggleHelp = useWorkspaceStore((s) => s.toggleHelp);
  const toggleGraphFullscreen = useWorkspaceStore((s) => s.toggleGraphFullscreen);
  const { setTheme, resolvedTheme } = useTheme();
  const loadIntake = useIntakeStore((s) => s.loadIntake);
  const resetIntake = useIntakeStore((s) => s.reset);

  const run = React.useCallback(
    (fn: () => void) => {
      fn();
      setOpen(false);
    },
    [setOpen],
  );

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="Type a command or search…" />
      <CommandList>
        <CommandEmpty>No commands found.</CommandEmpty>

        <CommandGroup heading="Diagnosis">
          <CommandItem
            onSelect={() =>
              run(() => {
                resetIntake();
                // Focus the symptom input on the next tick, after the palette closes
                setTimeout(() => {
                  const el = document.querySelector<HTMLInputElement>(
                    'input[aria-label="Symptoms"]',
                  );
                  el?.focus();
                }, 50);
                toast.success("Started new diagnosis");
                logger.info("command.new_diagnosis");
              })
            }
          >
            <Plus />
            New diagnosis
            <CommandShortcut>Ctrl N</CommandShortcut>
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="Example cases">
          {EXAMPLE_CASES.map((example) => (
            <CommandItem
              key={example.id}
              onSelect={() =>
                run(() => {
                  loadIntake(example.intake);
                  toast.success(`Loaded: ${example.label}`);
                  logger.info("command.example_loaded", { id: example.id });
                })
              }
            >
              <Stethoscope />
              <div className="flex flex-col">
                <span>{example.label}</span>
                <span className="text-muted-foreground text-xs">{example.description}</span>
              </div>
            </CommandItem>
          ))}
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="Workspace">
          <CommandItem
            onSelect={() =>
              run(() => {
                toggleGraphFullscreen();
              })
            }
          >
            <Maximize2 />
            Toggle fullscreen graph
            <CommandShortcut>F</CommandShortcut>
          </CommandItem>
          <CommandItem
            onSelect={() =>
              run(() => {
                setTheme(resolvedTheme === "dark" ? "light" : "dark");
              })
            }
          >
            {resolvedTheme === "dark" ? <Sun /> : <Moon />}
            Toggle theme
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="Help">
          <CommandItem onSelect={() => run(() => toggleHelp())}>
            <HelpCircle />
            Keyboard shortcuts
            <CommandShortcut>?</CommandShortcut>
          </CommandItem>
          <CommandItem
            onSelect={() =>
              run(() => {
                window.open("https://cloud.langfuse.com", "_blank", "noopener");
              })
            }
          >
            <Beaker />
            Open Langfuse traces
          </CommandItem>
          <CommandItem
            onSelect={() =>
              run(() => {
                window.open("http://localhost:8000/docs", "_blank", "noopener");
              })
            }
          >
            <FileText />
            API documentation
          </CommandItem>
          <CommandItem
            onSelect={() =>
              run(() => {
                window.location.reload();
              })
            }
          >
            <RotateCcw />
            Reload application
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
