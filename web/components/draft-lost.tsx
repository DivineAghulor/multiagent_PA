import Link from "next/link";

/**
 * S-3: drafts live in the backend's memory, so a restart (or the 12-hour idle
 * timeout, or confirming in another tab) loses them. That gets its own state
 * rather than a generic error, because the fix is simply to start again.
 */
export function DraftLost({ what, restartHref }: { what: string; restartHref: string }) {
  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 px-5 py-4 dark:border-amber-900 dark:bg-amber-950/40">
      <p className="text-sm font-semibold text-amber-900 dark:text-amber-200">This {what} was lost</p>
      <p className="mt-1 text-sm text-amber-800 dark:text-amber-300">
        Unconfirmed drafts are kept in the server&apos;s memory only. It was restarted, the draft sat
        idle too long, or it was already confirmed or discarded. Nothing from it was saved.
      </p>
      <Link
        href={restartHref}
        className="mt-3 inline-flex rounded-md bg-amber-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-amber-800 dark:bg-amber-200 dark:text-amber-950"
      >
        Start again
      </Link>
    </div>
  );
}
