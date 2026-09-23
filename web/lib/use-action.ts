"use client";

import { useRouter } from "next/navigation";
import { useCallback, useRef, useState, useTransition } from "react";
import { ApiError } from "./api";

/** The message to show for a failed call, in the user's terms. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

export function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

/**
 * Pending/error state around one write, followed by `router.refresh()` so the
 * server-rendered screen re-reads the database. `run` resolves to the call's
 * result, or undefined when it failed (the error is in `error`).
 *
 * `cancel` aborts an in-flight call that was given the signal — for the model
 * calls, which can take a while (NFR-1). A cancelled call is not an error.
 */
export function useAction() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, startRefresh] = useTransition();
  const controller = useRef<AbortController | null>(null);

  const run = useCallback(
    async <T,>(
      call: (signal: AbortSignal) => Promise<T>,
      { refresh = true }: { refresh?: boolean } = {},
    ): Promise<T | undefined> => {
      controller.current?.abort();
      const ctrl = new AbortController();
      controller.current = ctrl;
      setBusy(true);
      setError(null);
      try {
        const result = await call(ctrl.signal);
        if (refresh) startRefresh(() => router.refresh());
        return result;
      } catch (err) {
        if (!isAbort(err)) setError(errorMessage(err));
        return undefined;
      } finally {
        if (controller.current === ctrl) {
          controller.current = null;
          setBusy(false);
        }
      }
    },
    [router],
  );

  const cancel = useCallback(() => {
    controller.current?.abort();
    controller.current = null;
    setBusy(false);
  }, []);

  return { run, cancel, busy, refreshing, error, setError };
}
