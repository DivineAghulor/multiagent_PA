import { ApiError } from "@/lib/api";

/**
 * Every screen renders its failure the same way, and an unreachable backend is
 * called out separately from a request the backend rejected — they need
 * different things from the reader.
 */
export function ApiErrorPanel({ error }: { error: unknown }) {
  const isApi = error instanceof ApiError;
  const unreachable = isApi && error.isUnreachable;
  const message = isApi ? error.message : "Something went wrong loading this screen.";

  return (
    <div className="rounded-lg border border-red-300 bg-red-50 px-5 py-4 dark:border-red-900 dark:bg-red-950/40">
      <p className="text-sm font-semibold text-red-900 dark:text-red-200">
        {unreachable ? "The backend isn't running" : "Couldn't load this screen"}
      </p>
      <p className="mt-1 text-sm text-red-800 dark:text-red-300">{message}</p>
      {unreachable ? (
        <p className="mt-2 font-mono text-xs text-red-700 dark:text-red-400">
          uv run uvicorn api.main:app --reload
        </p>
      ) : null}
    </div>
  );
}
