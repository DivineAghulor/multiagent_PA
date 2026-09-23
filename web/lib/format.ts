import type { Task, TaskPriority, TaskStatus } from "./types";

export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function formatTimestamp(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Calendar arithmetic on ISO dates. Done in UTC throughout: mixing a local
 * midnight with toISOString() shifts the date by a day east of UTC. */
export function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** Monday of the week containing an ISO date. */
export function mondayOf(iso: string): string {
  const weekday = (new Date(`${iso}T00:00:00Z`).getUTCDay() + 6) % 7; // Monday = 0
  return addDays(iso, -weekday);
}

export const STATUS_ORDER: TaskStatus[] = [
  "backlog",
  "todo",
  "in_progress",
  "blocked",
  "done",
  "cancelled",
];

export const STATUS_LABELS: Record<TaskStatus, string> = {
  backlog: "Backlog",
  todo: "To do",
  in_progress: "In progress",
  blocked: "Blocked",
  done: "Done",
  cancelled: "Cancelled",
};

export const PRIORITY_LABELS: Record<TaskPriority, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
  urgent: "Urgent",
};

/**
 * How a task's rating reads in the UI. An unrated task shares the `medium`
 * priority bucket with "urgent but not important", so the pair — not the
 * bucket — decides what is shown.
 */
export function ratingLabel(task: Task): string {
  if (task.importance === null || task.urgency === null) return "Unrated";
  return `I${task.importance} · U${task.urgency}`;
}

/** Sort key for the importance/urgency ordering FR-3 asks for: most important
 * first, urgency breaking ties, unrated tasks last. */
export function byRatingDesc(a: Task, b: Task): number {
  const rank = (t: Task) =>
    t.importance === null || t.urgency === null ? -1 : t.importance * 10 + t.urgency;
  return rank(b) - rank(a);
}

export function byCreatedDesc(a: Task, b: Task): number {
  return b.created_at.localeCompare(a.created_at);
}
