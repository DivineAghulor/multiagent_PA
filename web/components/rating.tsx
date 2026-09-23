"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ErrorText } from "@/components/ui/field";
import { actions } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useAction } from "@/lib/use-action";
import type { Task } from "@/lib/types";

const LEVELS = [1, 2, 3, 4] as const;

/** Four buttons for one axis of the rating, 1 (lowest) to 4 (highest). */
export function RatingPicker({
  label,
  value,
  onChange,
  disabled,
}: {
  label: "Importance" | "Urgency";
  value: number | null;
  onChange: (value: number) => void;
  disabled?: boolean;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="flex items-center gap-1.5">
      <span className="w-20 text-xs text-neutral-500 dark:text-neutral-400">{label}</span>
      {LEVELS.map((level) => (
        <button
          key={level}
          type="button"
          role="radio"
          aria-checked={value === level}
          aria-label={`${label} ${level}`}
          disabled={disabled}
          onClick={() => onChange(level)}
          className={cn(
            "h-7 w-7 rounded-md border text-xs font-medium tabular-nums transition-colors disabled:opacity-50",
            value === level
              ? "border-neutral-900 bg-neutral-900 text-white dark:border-neutral-100 dark:bg-neutral-100 dark:text-neutral-900"
              : "border-neutral-300 hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800",
          )}
        >
          {level}
        </button>
      ))}
    </div>
  );
}

/** Rate one task. The priority bucket is derived server-side from the pair. */
export function RatingForm({
  task,
  onDone,
  onSkip,
  skipLabel = "Skip",
}: {
  task: Task;
  onDone: (task: Task) => void;
  onSkip?: () => void;
  skipLabel?: string;
}) {
  const [importance, setImportance] = useState<number | null>(task.importance);
  const [urgency, setUrgency] = useState<number | null>(task.urgency);
  const { run, busy, error } = useAction();

  const save = async () => {
    if (importance === null || urgency === null) return;
    const saved = await run(() => actions.rateTask(task.id, importance, urgency));
    if (saved) onDone(saved);
  };

  return (
    <div className="space-y-2">
      <RatingPicker label="Importance" value={importance} onChange={setImportance} disabled={busy} />
      <RatingPicker label="Urgency" value={urgency} onChange={setUrgency} disabled={busy} />
      <div className="flex gap-2 pt-1">
        <Button
          variant="primary"
          size="sm"
          onClick={save}
          disabled={busy || importance === null || urgency === null}
        >
          {busy ? "Saving…" : "Save rating"}
        </Button>
        {onSkip ? (
          <Button variant="ghost" size="sm" onClick={onSkip} disabled={busy}>
            {skipLabel}
          </Button>
        ) : null}
      </div>
      <ErrorText>{error}</ErrorText>
    </div>
  );
}

/**
 * FR-2: tasks waiting for a rating, one card each. Saving or skipping drops a
 * task from the queue; a skipped task stays unrated.
 */
export function RatingQueue({
  tasks,
  onEmpty,
}: {
  tasks: Task[];
  onEmpty?: () => void;
}) {
  const [queue, setQueue] = useState(tasks);

  const drop = (id: number) => {
    const next = queue.filter((t) => t.id !== id);
    setQueue(next);
    if (next.length === 0) onEmpty?.();
  };

  if (queue.length === 0) return null;

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between">
        <p className="text-sm font-medium">
          Rate {queue.length === 1 ? "this task" : `these ${queue.length} tasks`}
        </p>
        <Button variant="ghost" size="sm" onClick={() => { setQueue([]); onEmpty?.(); }}>
          Skip all
        </Button>
      </div>
      <ul className="space-y-3">
        {queue.map((task) => (
          <li
            key={task.id}
            className="rounded-lg border border-neutral-200 px-4 py-3 dark:border-neutral-800"
          >
            <p className="mb-2 text-sm font-medium">{task.title}</p>
            {task.description ? (
              <p className="mb-2 text-xs text-neutral-500 dark:text-neutral-400">{task.description}</p>
            ) : null}
            <RatingForm task={task} onDone={() => drop(task.id)} onSkip={() => drop(task.id)} />
          </li>
        ))}
      </ul>
    </div>
  );
}
