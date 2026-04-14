import { Activity, Circle, Command, HelpCircle, Moon, Sun } from "lucide-react";
import { motion } from "framer-motion";

import { useTheme } from "@/hooks/useTheme";
import { useWorkspaceStore } from "@/features/diagnosis/store/workspace";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Separator } from "@/components/ui/separator";
import { APP_NAME, APP_TAGLINE } from "@/lib/constants";

interface TopBarProps {
  connectionStatus: "connected" | "disconnected" | "checking";
}

export function TopBar({ connectionStatus }: TopBarProps) {
  const { resolvedTheme, toggleTheme } = useTheme();
  const toggleCommandPalette = useWorkspaceStore((s) => s.toggleCommandPalette);
  const toggleHelp = useWorkspaceStore((s) => s.toggleHelp);

  const statusColor = {
    connected: "text-[hsl(var(--success))]",
    checking: "text-[hsl(var(--warning))]",
    disconnected: "text-destructive",
  }[connectionStatus];

  return (
    <header className="sticky top-0 z-40 flex h-12 shrink-0 items-center gap-3 border-b border-border bg-background/80 px-4 backdrop-blur-md">
      {/* Brand */}
      <div className="flex items-center gap-2">
        <motion.div
          initial={{ rotate: -90, opacity: 0 }}
          animate={{ rotate: 0, opacity: 1 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
          className="flex h-6 w-6 items-center justify-center rounded-md bg-primary/15 text-primary"
        >
          <Activity className="h-3.5 w-3.5" strokeWidth={2.5} />
        </motion.div>
        <div className="flex items-baseline gap-2">
          <h1 className="text-sm font-semibold tracking-tight">{APP_NAME}</h1>
          <span className="hidden text-xs text-muted-foreground md:inline">
            {APP_TAGLINE}
          </span>
        </div>
      </div>

      <div className="flex-1" />

      {/* Command palette trigger */}
      <Button
        variant="outline"
        size="sm"
        className="hidden h-8 gap-2 px-3 text-xs text-muted-foreground sm:inline-flex"
        onClick={toggleCommandPalette}
        aria-label="Open command palette"
      >
        <Command className="h-3.5 w-3.5" />
        <span>Commands</span>
        <Kbd className="ml-2">Ctrl K</Kbd>
      </Button>

      <Separator orientation="vertical" className="h-5" />

      {/* Help */}
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={toggleHelp}
            aria-label="Keyboard shortcuts"
          >
            <HelpCircle className="h-3.5 w-3.5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          Shortcuts <Kbd className="ml-1">?</Kbd>
        </TooltipContent>
      </Tooltip>

      {/* Theme toggle */}
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={toggleTheme}
            aria-label={`Switch to ${resolvedTheme === "dark" ? "light" : "dark"} theme`}
          >
            {resolvedTheme === "dark" ? (
              <Sun className="h-3.5 w-3.5" />
            ) : (
              <Moon className="h-3.5 w-3.5" />
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom">Toggle theme</TooltipContent>
      </Tooltip>

      <Separator orientation="vertical" className="h-5" />

      {/* Connection status */}
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex items-center gap-1.5">
            <Circle
              className={`h-2 w-2 fill-current ${statusColor}`}
              strokeWidth={0}
            />
            <span className="hidden text-xs text-muted-foreground md:inline">
              API
            </span>
          </div>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          {connectionStatus === "connected"
            ? "Connected to backend"
            : connectionStatus === "checking"
              ? "Checking connection…"
              : "Backend offline"}
        </TooltipContent>
      </Tooltip>
    </header>
  );
}
