"use client";

import { useEffect, useRef } from "react";
import { cn } from "@/lib/cn";

/**
 * A modal on the native <dialog> element: focus trapping, Escape to close and
 * the backdrop come from the browser rather than from a dependency.
 */
export function Dialog({
  open,
  onClose,
  title,
  children,
  className,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => {
        // A click on the backdrop lands on the dialog element itself.
        if (e.target === ref.current) onClose();
      }}
      className={cn(
        "m-auto w-full max-w-md rounded-xl border border-neutral-200 bg-white p-0 text-neutral-900 shadow-xl",
        "backdrop:bg-black/40 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-100",
        className,
      )}
    >
      {open ? (
        <div className="space-y-4 p-5">
          <h2 className="text-base font-semibold tracking-tight">{title}</h2>
          {children}
        </div>
      ) : null}
    </dialog>
  );
}
