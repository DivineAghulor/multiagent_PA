import { cn } from "@/lib/cn";

export function Progress({
  value,
  max,
  className,
}: {
  value: number;
  max: number | null;
  className?: string;
}) {
  // A goal with no target isn't measurable; showing a 0% bar for it would
  // read as failure rather than as "no target set".
  if (max === null || max <= 0) return null;
  const pct = Math.min(100, Math.round((value / max) * 100));
  return (
    <div
      className={cn(
        "h-1.5 w-full overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-800",
        className,
      )}
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={max}
    >
      <div
        className={cn("h-full rounded-full", pct >= 100 ? "bg-green-600" : "bg-blue-600")}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
