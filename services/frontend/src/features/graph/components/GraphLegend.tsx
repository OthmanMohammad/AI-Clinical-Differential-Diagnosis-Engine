import { ENTITY_COLOR_VAR, ENTITY_LABELS, ENTITY_TYPES } from "@/lib/constants";
import { cn } from "@/lib/utils";

interface GraphLegendProps {
  visibleTypes?: Set<string>;
  onToggle?: (type: string) => void;
  className?: string;
}

export function GraphLegend({ visibleTypes, onToggle, className }: GraphLegendProps) {
  return (
    <div
      className={cn(
        "pointer-events-auto flex flex-wrap items-center gap-1.5 rounded-md border border-border bg-card/80 px-2 py-1.5 shadow-sm backdrop-blur",
        className,
      )}
    >
      {ENTITY_TYPES.map((type) => {
        const isVisible = visibleTypes ? visibleTypes.has(type) : true;
        return (
          <button
            key={type}
            type="button"
            onClick={() => onToggle?.(type)}
            className={cn(
              "inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[10px] font-medium transition-opacity",
              !isVisible && "opacity-35",
              onToggle && "hover:bg-muted",
            )}
            aria-pressed={isVisible}
          >
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: `hsl(var(${ENTITY_COLOR_VAR[type]}))` }}
            />
            <span className="capitalize">{ENTITY_LABELS[type]}</span>
          </button>
        );
      })}
    </div>
  );
}
