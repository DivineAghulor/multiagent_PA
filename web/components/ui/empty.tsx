import { cn } from "@/lib/cn";

/** The same shape for every "there is nothing here yet" state, so an empty
 * screen never reads as a failed one. */
export function Empty({
  title,
  hint,
  className,
}: {
  title: string;
  hint?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border border-dashed border-neutral-300 px-5 py-8 text-center dark:border-neutral-700",
        className,
      )}
    >
      <p className="text-sm font-medium text-neutral-700 dark:text-neutral-300">{title}</p>
      {hint ? (
        <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">{hint}</p>
      ) : null}
    </div>
  );
}
