import {
  Activity,
  BookOpen,
  FlaskConical,
  History,
  Settings,
  Stethoscope,
} from "lucide-react";
import { motion } from "framer-motion";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

interface NavItem {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  href?: string;
  active?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { icon: Stethoscope, label: "Diagnose", active: true },
  { icon: History, label: "History" },
  { icon: FlaskConical, label: "Eval" },
  { icon: BookOpen, label: "Knowledge Graph" },
];

export function Sidebar() {
  return (
    <aside className="flex w-14 shrink-0 flex-col border-r border-border bg-card">
      <nav className="flex flex-1 flex-col items-center gap-1 p-2">
        {NAV_ITEMS.map((item, idx) => (
          <SidebarItem
            key={item.label}
            {...item}
            delay={idx * 0.04}
          />
        ))}
      </nav>

      <div className="flex flex-col items-center gap-1 p-2">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="Settings">
              <Settings className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="right">Settings</TooltipContent>
        </Tooltip>
      </div>
    </aside>
  );
}

interface SidebarItemProps extends NavItem {
  delay?: number;
}

function SidebarItem({ icon: Icon, label, active, delay = 0 }: SidebarItemProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <motion.button
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay, duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
          type="button"
          className={cn(
            "relative flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground transition-colors",
            "hover:bg-accent hover:text-accent-foreground",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
            active && "bg-primary/10 text-primary",
          )}
          aria-label={label}
          aria-current={active ? "page" : undefined}
        >
          <Icon className="h-4 w-4" />
          {active && (
            <motion.span
              layoutId="sidebar-active"
              className="absolute -left-2 h-5 w-1 rounded-r-full bg-primary"
              transition={{ type: "spring", stiffness: 500, damping: 35 }}
            />
          )}
        </motion.button>
      </TooltipTrigger>
      <TooltipContent side="right" className="flex items-center gap-2">
        <Activity className="h-3 w-3" />
        {label}
      </TooltipContent>
    </Tooltip>
  );
}
