"use client";

import { useState } from "react";
import { RatingForm } from "@/components/rating";
import { TaskEditDialog } from "@/components/task-edit-dialog";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { ErrorText, Select } from "@/components/ui/field";
import { actions } from "@/lib/api";
import { STATUS_LABELS, STATUS_ORDER } from "@/lib/format";
import { useAction } from "@/lib/use-action";
import type { Project, Task, TaskStatus } from "@/lib/types";

/** Tick box: completes, or reopens a done task (FR-17's unticking). */
export function TaskCheckbox({ task }: { task: Task }) {
  const { run, busy, error } = useAction();
  const done = task.status === "done";
  return (
    <input
      type="checkbox"
      className="h-4 w-4 cursor-pointer accent-green-600 disabled:cursor-wait"
      checked={done}
      disabled={busy}
      title={error ?? (done ? "Reopen" : "Mark done")}
      aria-label={done ? `Reopen ${task.title}` : `Complete ${task.title}`}
      onChange={() => run(() => (done ? actions.reopenTask(task.id) : actions.completeTask(task.id)))}
    />
  );
}

export function TaskStatusSelect({ task }: { task: Task }) {
  const { run, busy, error } = useAction();
  return (
    <Select
      aria-label={`Status of ${task.title}`}
      title={error ?? undefined}
      className="text-xs"
      value={task.status}
      disabled={busy}
      onChange={(e) => run(() => actions.setTaskStatus(task.id, e.target.value as TaskStatus))}
    >
      {STATUS_ORDER.map((s) => (
        <option key={s} value={s}>
          {STATUS_LABELS[s]}
        </option>
      ))}
    </Select>
  );
}

/** Edit / rate / delete for one task row (FR-4). Delete asks first. */
export function TaskRowMenu({ task, projects }: { task: Task; projects: Project[] }) {
  const [dialog, setDialog] = useState<"edit" | "rate" | "delete" | null>(null);
  const del = useAction();
  const close = () => setDialog(null);

  return (
    <div className="flex justify-end gap-1">
      <Button variant="ghost" size="sm" onClick={() => setDialog("edit")}>
        Edit
      </Button>
      <Button variant="ghost" size="sm" onClick={() => setDialog("rate")}>
        Rate
      </Button>
      <Button variant="ghost" size="sm" onClick={() => setDialog("delete")}>
        Delete
      </Button>

      <TaskEditDialog task={task} projects={projects} open={dialog === "edit"} onClose={close} />

      <Dialog open={dialog === "rate"} onClose={close} title={`Rate “${task.title}”`}>
        <RatingForm task={task} onDone={close} onSkip={close} skipLabel="Cancel" />
      </Dialog>

      <Dialog open={dialog === "delete"} onClose={close} title="Delete this task?">
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          “{task.title}” will be removed permanently. This can&apos;t be undone.
        </p>
        <ErrorText>{del.error}</ErrorText>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={close} disabled={del.busy}>
            Keep it
          </Button>
          <Button
            variant="danger"
            disabled={del.busy}
            onClick={async () => {
              const ok = await del.run(() => actions.deleteTask(task.id).then(() => true));
              if (ok) close();
            }}
          >
            {del.busy ? "Deleting…" : "Delete"}
          </Button>
        </div>
      </Dialog>
    </div>
  );
}
