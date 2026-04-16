import { cn } from "@/lib/utils";

function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("shimmer bg-muted/50 rounded-md", className)} {...props} />;
}

export { Skeleton };
