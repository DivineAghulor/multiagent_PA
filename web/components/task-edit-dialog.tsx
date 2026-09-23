"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { ErrorText, Field, Input, Select, Textarea } from "@/components/ui/field";
import { actions, api, type TaskEdit } from "@/lib/api";
import { useAction } from "@/lib/use-action";
import type { Milestone, Project, Task } from "@/lib/types";

/**
 * FR-4 edit: title, description, due date, project, milestone, and the day
 * it's scheduled for. Only changed fields are sent, so an edit never
 * overwrites a field the user didn't touch.
 */
export function TaskEditDialog({
  task,
  projects,
  open,
  onClose,
}: {
  task: Task;
  projects: Project[];
  open: boolean;
  onClose: () => void;
}) {
  const [title, setTitle] = useState(task.title);
  const [description, setDescription] = useState(task.description ?? "");
  const [dueDate, setDueDate] = useState(task.due_date ?? "");
  const [scheduledFor, setScheduledFor] = useState(task.scheduled_for ?? "");
  const [projectId, setProjectId] = useState<number | null>(task.project_id);
  const [milestoneId, setMilestoneId] = useState<number | null>(task.milestone_id);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const { run, busy, error } = useAction();

  // Reset to the task's current values each time the dialog opens.
  useEffect(() => {
    if (!open) return;
    setTitle(task.title);
    setDescription(task.description ?? "");
    setDueDate(task.due_date ?? "");
    setScheduledFor(task.scheduled_for ?? "");
    setProjectId(task.project_id);
    setMilestoneId(task.milestone_id);
  }, [open, task]);

  // A task's milestone must belong to its project, so the milestone list
  // follows the project picker.
  useEffect(() => {
    if (!open || projectId === null) {
      setMilestones([]);
      return;
    }
    let live = true;
    api
      .project(projectId)
      .then((p) => live && setMilestones(p.milestones))
      .catch(() => live && setMilestones([]));
    return () => {
      live = false;
    };
  }, [open, projectId]);

  const save = async () => {
    const edit: TaskEdit = {};
    if (title.trim() !== task.title) edit.title = title.trim();
    if ((description.trim() || null) !== task.description) edit.description = description.trim() || null;
    if ((dueDate || null) !== task.due_date) edit.due_date = dueDate || null;
    if (projectId !== task.project_id) edit.project_id = projectId;
    if (milestoneId !== task.milestone_id) edit.milestone_id = milestoneId;
    const reschedule = (scheduledFor || null) !== task.scheduled_for;

    const ok = await run(async () => {
      if (Object.keys(edit).length > 0) await actions.updateTask(task.id, edit);
      if (reschedule) await actions.scheduleTask(task.id, scheduledFor || null);
      return true;
    });
    if (ok) onClose();
  };

  return (
    <Dialog open={open} onClose={onClose} title="Edit task">
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          save();
        }}
      >
        <Field label="Title">
          <Input value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={300} />
        </Field>
        <Field label="Description">
          <Textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Due date">
            <Input type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
          </Field>
          <Field label="Scheduled for">
            <Input type="date" value={scheduledFor} onChange={(e) => setScheduledFor(e.target.value)} />
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Project">
            <Select
              className="w-full"
              value={projectId ?? ""}
              onChange={(e) => {
                setProjectId(e.target.value === "" ? null : Number(e.target.value));
                setMilestoneId(null);
              }}
            >
              <option value="">No project</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Milestone">
            <Select
              className="w-full"
              value={milestoneId ?? ""}
              disabled={projectId === null}
              onChange={(e) => setMilestoneId(e.target.value === "" ? null : Number(e.target.value))}
            >
              <option value="">No milestone</option>
              {milestones.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <ErrorText>{error}</ErrorText>
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={busy || !title.trim()}>
            {busy ? "Saving…" : "Save"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
