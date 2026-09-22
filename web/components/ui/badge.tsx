import { cn } from "@/lib/cn";

export type BadgeTone = "neutral" | "blue" | "amber" | "red" | "green";

const TONES: Record<BadgeTone, string> = {
  neutral:
    "bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300",
  blue: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300",
  amber: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-300",
  red: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  green: "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300",
};

export function Badge({
  tone = "neutral",
  className,
  ...props
}: React.ComponentProps<"span"> & { tone?: BadgeTone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-1.5 py-0.5 text-xs font-medium whitespace-nowrap",
        TONES[tone],
        className,
      )}
      {...props}
    />
  );
}
