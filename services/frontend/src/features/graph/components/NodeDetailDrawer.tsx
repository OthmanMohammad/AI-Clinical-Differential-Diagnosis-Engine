import { Copy, ExternalLink } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { useCopyToClipboard } from "@/hooks/useCopyToClipboard";
import { ENTITY_COLOR_VAR } from "@/lib/constants";
import { formatEdgeLabel } from "@/features/graph/config/edgeTypes";
import type { GraphEdge, GraphNode } from "@/types/api";

interface NodeDetailDrawerProps {
  node: GraphNode | null;
  allNodes: GraphNode[];
  allEdges: GraphEdge[];
  onClose: () => void;
}

export function NodeDetailDrawer({
  node,
  allNodes,
  allEdges,
  onClose,
}: NodeDetailDrawerProps) {
  const { copy, copied } = useCopyToClipboard();

  const neighbors = node
    ? allEdges
        .filter((e) => e.source === node.id || e.target === node.id)
        .map((e) => {
          const otherId = e.source === node.id ? e.target : e.source;
          const other = allNodes.find((n) => n.id === otherId);
          return {
            node: other,
            edgeType: e.type,
            direction: (e.source === node.id ? "out" : "in") as "out" | "in",
          };
        })
        .filter((n): n is { node: GraphNode; edgeType: string; direction: "out" | "in" } =>
          n.node !== undefined,
        )
    : [];

  return (
    <Sheet open={!!node} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-96 sm:max-w-md">
        {node && (
          <>
            <SheetHeader className="mb-4 space-y-3">
              <div className="flex items-center gap-2">
                <span
                  className="h-2 w-2 rounded-full"
                  style={{
                    backgroundColor:
                      node.type in ENTITY_COLOR_VAR
                        ? `hsl(var(${ENTITY_COLOR_VAR[node.type as keyof typeof ENTITY_COLOR_VAR]}))`
                        : "#888",
                  }}
                />
                <Badge variant="outline" className="text-[10px]">
                  {node.type}
                </Badge>
              </div>
              <SheetTitle className="text-lg">{node.name}</SheetTitle>
              <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                <span className="font-mono">{node.id.slice(0, 24)}…</span>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => void copy(node.id)}
                  aria-label="Copy ID"
                >
                  <Copy className="h-3 w-3" />
                </Button>
                {copied && <span className="text-[hsl(var(--success))]">Copied</span>}
              </div>
            </SheetHeader>

            <Separator />

            <ScrollArea className="mt-4 h-[calc(100vh-220px)] pr-4">
              <div className="space-y-4">
                <div>
                  <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Connections ({neighbors.length})
                  </h4>
                  <ul className="space-y-1">
                    {neighbors.map((n, i) => (
                      <li
                        key={`${n.node.id}-${i}`}
                        className="flex items-start gap-2 rounded-sm bg-muted/20 px-2 py-1.5 text-xs"
                      >
                        <span
                          className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full"
                          style={{
                            backgroundColor:
                              n.node.type in ENTITY_COLOR_VAR
                                ? `hsl(var(${
                                    ENTITY_COLOR_VAR[
                                      n.node.type as keyof typeof ENTITY_COLOR_VAR
                                    ]
                                  }))`
                                : "#888",
                          }}
                        />
                        <div className="flex-1">
                          <div className="truncate">{n.node.name}</div>
                          <div className="mt-0.5 text-[10px] text-muted-foreground">
                            <ExternalLink className="mr-1 inline h-2.5 w-2.5" />
                            {formatEdgeLabel(n.edgeType)} ({n.direction})
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </ScrollArea>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
