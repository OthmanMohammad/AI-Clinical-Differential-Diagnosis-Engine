import {
  Download,
  Layers,
  Maximize2,
  Minimize2,
  Search,
  ZoomIn,
  ZoomOut,
  Fullscreen,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Kbd } from "@/components/ui/kbd";
import { LAYOUT_LABELS, type LayoutType } from "@/features/graph/config/layouts";
import { cn } from "@/lib/utils";

interface GraphToolbarProps {
  layout: LayoutType;
  onLayoutChange: (layout: LayoutType) => void;
  onFit: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onSearch: () => void;
  onExportPng: () => void;
  onToggleFullscreen: () => void;
  fullscreen: boolean;
  className?: string;
}

export function GraphToolbar({
  layout,
  onLayoutChange,
  onFit,
  onZoomIn,
  onZoomOut,
  onSearch,
  onExportPng,
  onToggleFullscreen,
  fullscreen,
  className,
}: GraphToolbarProps) {
  return (
    <div
      className={cn(
        "pointer-events-auto flex items-center gap-0.5 rounded-md border border-border bg-card/80 p-0.5 shadow-sm backdrop-blur",
        className,
      )}
    >
      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="ghost" size="icon-sm" onClick={onFit} aria-label="Fit to screen">
            <Fullscreen className="h-3.5 w-3.5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          Fit to screen <Kbd className="ml-1">0</Kbd>
        </TooltipContent>
      </Tooltip>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="ghost" size="icon-sm" onClick={onZoomIn} aria-label="Zoom in">
            <ZoomIn className="h-3.5 w-3.5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          Zoom in <Kbd className="ml-1">+</Kbd>
        </TooltipContent>
      </Tooltip>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="ghost" size="icon-sm" onClick={onZoomOut} aria-label="Zoom out">
            <ZoomOut className="h-3.5 w-3.5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          Zoom out <Kbd className="ml-1">-</Kbd>
        </TooltipContent>
      </Tooltip>

      <div className="mx-0.5 h-4 w-px bg-border" />

      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="ghost" size="icon-sm" onClick={onSearch} aria-label="Search nodes">
            <Search className="h-3.5 w-3.5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          Search nodes <Kbd className="ml-1">Ctrl F</Kbd>
        </TooltipContent>
      </Tooltip>

      <DropdownMenu>
        <Tooltip>
          <TooltipTrigger asChild>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label="Layout">
                <Layers className="h-3.5 w-3.5" />
              </Button>
            </DropdownMenuTrigger>
          </TooltipTrigger>
          <TooltipContent side="bottom">Layout</TooltipContent>
        </Tooltip>
        <DropdownMenuContent align="end" className="w-40">
          <DropdownMenuLabel>Layout</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuRadioGroup
            value={layout}
            onValueChange={(v) => onLayoutChange(v as LayoutType)}
          >
            {(Object.keys(LAYOUT_LABELS) as LayoutType[]).map((l) => (
              <DropdownMenuRadioItem key={l} value={l} className="text-xs">
                {LAYOUT_LABELS[l]}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="ghost" size="icon-sm" onClick={onExportPng} aria-label="Export PNG">
            <Download className="h-3.5 w-3.5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom">Export PNG</TooltipContent>
      </Tooltip>

      <div className="mx-0.5 h-4 w-px bg-border" />

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onToggleFullscreen}
            aria-label="Toggle fullscreen"
          >
            {fullscreen ? (
              <Minimize2 className="h-3.5 w-3.5" />
            ) : (
              <Maximize2 className="h-3.5 w-3.5" />
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          Fullscreen <Kbd className="ml-1">F</Kbd>
        </TooltipContent>
      </Tooltip>
    </div>
  );
}
