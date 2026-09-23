"use client";

import { Badge } from "@/components/ui/badge";
import { formatDate } from "@/lib/format";
import type { Draft } from "@/lib/types";

export interface Exclusions {
  milestones: Set<string>;
  tasks: Set<string>;
}

/**
 * FR-13: the draft as a milestone/task outline, telling apart what's already
 * in the database from what confirming would add. New items carry an include
 * checkbox; unticked ones are left out of the confirm.
 */
export function DraftOutline({
  draft,
  excluded,
  onToggle,
  disabled,
}: {
  draft: Draft;
  excluded: Exclusions;
  onToggle: (kind: "milestones" | "tasks", ref: string) => void;
  disabled?: boolean;
}) {
  if (draft.milestones.length === 0) {
    return (
      <p className="text-sm text-neutral-500 dark:text-neutral-400">
        No milestones yet. Describe the project and the assistant will draft them.
      </p>
    );
  }

  return (
    <ol className="space-y-3">
      {draft.milestones.map((m, i) => {
        const existing = m.existing_id !== null;
        const milestoneOut = !existing && excluded.milestones.has(m.ref);
        return (
          <li
            key={m.ref}
            className="rounded-lg border border-neutral-200 px-4 py-3 dark:border-neutral-800"
          >
            <label className="flex items-start gap-2">
              {existing ? (
                <span className="mt-0.5 h-4 w-4 shrink-0" />
              ) : (
                <input
                  type="checkbox"
                  className="mt-0.5 h-4 w-4 shrink-0"
                  checked={!milestoneOut}
                  disabled={disabled}
                  onChange={() => onToggle("milestones", m.ref)}
                  aria-label={`Include milestone ${m.name}`}
                />
              )}
              <span className={milestoneOut ? "line-through opacity-50" : ""}>
                <span className="text-sm font-medium">
                  {i + 1}. {m.name}
                </span>{" "}
                <span className="font-mono text-xs text-neutral-400">{m.ref}</span>{" "}
                {existing ? <Badge tone="neutral">existing</Badge> : <Badge tone="green">new</Badge>}
                {m.due_date ? (
                  <span className="ml-2 text-xs text-neutral-500">due {formatDate(m.due_date)}</span>
                ) : null}
                {m.description ? (
                  <span className="block text-xs text-neutral-500 dark:text-neutral-400">{m.description}</span>
                ) : null}
              </span>
            </label>

            <ul className="mt-2 space-y-1 pl-6">
              {m.existing_task_titles.map((title) => (
                <li key={`db-${title}`} className="text-sm text-neutral-500 dark:text-neutral-400">
                  · {title} <span className="text-xs">(already in project)</span>
                </li>
              ))}
              {m.tasks.map((t) => {
                const out = milestoneOut || excluded.tasks.has(t.ref);
                return (
                  <li key={t.ref}>
                    <label className="flex items-start gap-2 text-sm">
                      <input
                        type="checkbox"
                        className="mt-0.5 h-3.5 w-3.5 shrink-0"
                        checked={!out}
                        disabled={disabled || milestoneOut}
                        onChange={() => onToggle("tasks", t.ref)}
                        aria-label={`Include task ${t.title}`}
                      />
                      <span className={out ? "line-through opacity-50" : ""}>
                        {t.title}{" "}
                        <span className="font-mono text-xs text-neutral-400">{t.ref}</span>
                        {t.existing_task_id !== null ? (
                          <Badge className="ml-1" tone="blue">
                            attach existing
                          </Badge>
                        ) : null}
                      </span>
                    </label>
                  </li>
                );
              })}
              {m.tasks.length === 0 && m.existing_task_titles.length === 0 ? (
                <li className="text-xs text-amber-700 dark:text-amber-400">
                  No tasks — a new milestone needs at least one to be confirmed.
                </li>
              ) : null}
            </ul>
          </li>
        );
      })}
    </ol>
  );
}
