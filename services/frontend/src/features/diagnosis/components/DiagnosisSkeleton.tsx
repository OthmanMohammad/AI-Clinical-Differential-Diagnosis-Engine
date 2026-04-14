import { Skeleton } from "@/components/ui/skeleton";

/**
 * Content-shaped skeleton that matches the DiagnosisCard layout.
 */
export function DiagnosisSkeleton() {
  return (
    <div className="space-y-3">
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="rounded-lg border border-border bg-card p-4"
        >
          <div className="flex items-start gap-3">
            <Skeleton className="h-7 w-7 rounded-md" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-1.5 w-full" />
            </div>
            <Skeleton className="h-5 w-16" />
          </div>
          <div className="mt-3 space-y-1.5 pt-2">
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-5/6" />
          </div>
        </div>
      ))}
    </div>
  );
}
