import { cn } from "@/lib/cn";

const CONTROL =
  "w-full rounded-md border border-neutral-300 bg-white px-2.5 py-1.5 text-sm " +
  "placeholder:text-neutral-400 focus:border-neutral-500 focus:outline-none " +
  "disabled:opacity-60 dark:border-neutral-700 dark:bg-neutral-900 dark:placeholder:text-neutral-500";

export function Input({ className, ...props }: React.ComponentProps<"input">) {
  return <input className={cn(CONTROL, className)} {...props} />;
}

export function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return <textarea className={cn(CONTROL, "resize-y", className)} {...props} />;
}

export function Select({ className, ...props }: React.ComponentProps<"select">) {
  return <select className={cn(CONTROL, "w-auto py-1", className)} {...props} />;
}

/** A labelled control. The label wraps the control, so no id wiring is needed. */
export function Field({
  label,
  hint,
  className,
  children,
}: {
  label: string;
  hint?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <label className={cn("block space-y-1", className)}>
      <span className="text-xs font-medium text-neutral-600 dark:text-neutral-400">{label}</span>
      {children}
      {hint ? <span className="block text-xs text-neutral-500">{hint}</span> : null}
    </label>
  );
}

/** An inline failure next to the control that caused it. */
export function ErrorText({ children }: { children: React.ReactNode }) {
  if (!children) return null;
  return (
    <p role="alert" className="text-sm text-red-700 dark:text-red-400">
      {children}
    </p>
  );
}
