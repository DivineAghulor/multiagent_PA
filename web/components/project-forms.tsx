"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { ErrorText, Field, Input, Select, Textarea } from "@/components/ui/field";
import { actions, type ProjectEdit } from "@/lib/api";
import { useAction } from "@/lib/use-action";
import type { Milestone, MilestoneStatus, Project, ProjectStatus } from "@/lib/types";

const PROJECT_STATUSES: ProjectStatus[] = ["active", "on_hold", "completed", "archived"];
const MILESTONE_STATUSES: MilestoneStatus[] = ["planned", "in_progress", "done"];

const label = (s: string) => s.replace("_", " ");

/** FR-23 create. A new project has no milestones; breaking it down is the
 * decomposition screen's job, offered straight after. */
export function NewProjectForm() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [targetDate, setTargetDate] = useState("");
  const { run, busy, error } = useAction();

  const create = async () => {
    const project = await run(
      () =>
        actions.createProject({
          name: name.trim(),
          description: description.trim() || null,
          target_date: targetDate || null,
        }),
      { refresh: false },
    );
    if (project) router.push(`/projects/${project.id}`);
  };

  if (!open) {
    return (
      <Button variant="primary" onClick={() => setOpen(true)}>
        New project
      </Button>
    );
  }

  return (
    <form
      className="space-y-3 rounded-xl border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-neutral-900"
      onSubmit={(e) => {
        e.preventDefault();
        create();
      }}
    >
      <Field label="Name">
        <Input value={name} onChange={(e) => setName(e.target.value)} required maxLength={300} autoFocus />
      </Field>
      <Field label="Description" hint="The decomposition model reads this, so say what done looks like.">
        <Textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
      </Field>
      <Field label="Target date" className="max-w-48">
        <Input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
      </Field>
      <ErrorText>{error}</ErrorText>
      <div className="flex gap-2">
        <Button type="submit" variant="primary" disabled={busy || !name.trim()}>
          {busy ? "Creating…" : "Create project"}
        </Button>
        <Button variant="ghost" onClick={() => setOpen(false)} disabled={busy}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

/** Edit / archive controls on the project detail screen. */
export function ProjectControls({ project }: { project: Project }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(project.name);
  const [description, setDescription] = useState(project.description ?? "");
  const [status, setStatus] = useState<ProjectStatus>(project.status);
  const [targetDate, setTargetDate] = useState(project.target_date ?? "");
  const save = useAction();
  const archive = useAction();

  const openEditor = () => {
    setName(project.name);
    setDescription(project.description ?? "");
    setStatus(project.status);
    setTargetDate(project.target_date ?? "");
    setEditing(true);
  };

  const submit = async () => {
    const edit: ProjectEdit = {};
    if (name.trim() !== project.name) edit.name = name.trim();
    if ((description.trim() || null) !== project.description) edit.description = description.trim() || null;
    if (status !== project.status) edit.status = status;
    if ((targetDate || null) !== project.target_date) edit.target_date = targetDate || null;
    if (Object.keys(edit).length === 0) return setEditing(false);
    const ok = await save.run(() => actions.updateProject(project.id, edit));
    if (ok) setEditing(false);
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      {project.status !== "archived" ? (
        <Link
          href={`/decompose?project=${project.id}`}
          className="inline-flex items-center rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-700 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-300"
        >
          Break down with the assistant
        </Link>
      ) : null}
      <Button onClick={openEditor}>Edit</Button>
      {project.status === "archived" ? (
        <Button
          disabled={archive.busy}
          onClick={() => archive.run(() => actions.updateProject(project.id, { status: "active" }))}
        >
          Restore
        </Button>
      ) : (
        <Button disabled={archive.busy} onClick={() => archive.run(() => actions.archiveProject(project.id))}>
          Archive
        </Button>
      )}
      <ErrorText>{archive.error}</ErrorText>

      <Dialog open={editing} onClose={() => setEditing(false)} title="Edit project">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <Field label="Name">
            <Input value={name} onChange={(e) => setName(e.target.value)} required maxLength={300} />
          </Field>
          <Field label="Description">
            <Textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Status">
              <Select className="w-full" value={status} onChange={(e) => setStatus(e.target.value as ProjectStatus)}>
                {PROJECT_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {label(s)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Target date">
              <Input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
            </Field>
          </div>
          <ErrorText>{save.error}</ErrorText>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setEditing(false)} disabled={save.busy}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={save.busy || !name.trim()}>
              {save.busy ? "Saving…" : "Save"}
            </Button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}

/** FR-25: milestone status straight from its card header. */
export function MilestoneStatusSelect({ milestone }: { milestone: Milestone }) {
  const { run, busy, error } = useAction();
  return (
    <Select
      aria-label={`Status of ${milestone.name}`}
      title={error ?? undefined}
      className="text-xs"
      value={milestone.status}
      disabled={busy}
      onChange={(e) => run(() => actions.setMilestoneStatus(milestone.id, e.target.value as MilestoneStatus))}
    >
      {MILESTONE_STATUSES.map((s) => (
        <option key={s} value={s}>
          {label(s)}
        </option>
      ))}
    </Select>
  );
}
