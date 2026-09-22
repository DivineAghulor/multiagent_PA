"use client";

import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Empty } from "@/components/ui/empty";
import {
  PRIORITY_LABELS,
  STATUS_LABELS,
  byCreatedDesc,
  byRatingDesc,
  formatDate,
  ratingLabel,
} from "@/lib/format";
import { PRIORITY_TONES } from "@/lib/tones";
import type { Project, Task, TaskStatus } from "@/lib/types";

const STATUS_ORDER: TaskStatus[] = [
  "backlog",
  "todo",
  "in_progress",
  "blocked",
  "done",
  "cancelled",
];

type Sort = "rating" | "created";

const SELECT_CLASS =
  "rounded-md border border-neutral-300 bg-white px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900";

/**
 * Filtering and sorting happen here rather than server-side: this is one
 * person's task list, it arrives whole, and re-sorting it in the browser keeps
 * ordering logic out of the API (see api/routers/tasks.py).
 *
 * Read-only for W1 — completing, editing and deleting arrive in W2 with the
 * tools/tasks.py stubs they need.
 */
export function TaskTable({ tasks, projects }: { tasks: Task[]; projects: Project[] }) {
  const [status, setStatus] = useState<TaskStatus | "all">("all");
  const [projectId, setProjectId] = useState<number | "all">("all");
  const [sort, setSort] = useState<Sort>("rating");

  const projectNames = useMemo(
    () => new Map(projects.map((p) => [p.id, p.name])),
    [projects],
  );

  const visible = useMemo(() => {
    const filtered = tasks.filter(
      (task) =>
        (status === "all" || task.status === status) &&
        (projectId === "all" || task.project_id === projectId),
    );
    return [...filtered].sort(sort === "rating" ? byRatingDesc : byCreatedDesc);
  }, [tasks, status, projectId, sort]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <select
          aria-label="Filter by status"
          className={SELECT_CLASS}
          value={status}
          onChange={(e) => setStatus(e.target.value as TaskStatus | "all")}
        >
          <option value="all">All statuses</option>
          {STATUS_ORDER.map((value) => (
            <option key={value} value={value}>
              {STATUS_LABELS[value]}
            </option>
          ))}
        </select>

        <select
          aria-label="Filter by project"
          className={SELECT_CLASS}
          value={projectId}
          onChange={(e) =>
            setProjectId(e.target.value === "all" ? "all" : Number(e.target.value))
          }
        >
          <option value="all">All projects</option>
          {projects.map((project) => (
            <option key={project.id} value={project.id}>
              {project.name}
            </option>
          ))}
        </select>

        <select
          aria-label="Sort by"
          className={SELECT_CLASS}
          value={sort}
          onChange={(e) => setSort(e.target.value as Sort)}
        >
          <option value="rating">Most important first</option>
          <option value="created">Newest first</option>
        </select>

        <span className="ml-auto text-sm text-neutral-500 dark:text-neutral-400">
          {visible.length} of {tasks.length}
        </span>
      </div>

      {visible.length === 0 ? (
        <Empty
          title={tasks.length === 0 ? "No tasks yet" : "No tasks match these filters"}
          hint={
            tasks.length === 0
              ? "Capturing tasks from freeform text arrives in W2."
              : undefined
          }
        />
      ) : (
        <div className="overflow-x-auto rounded-xl border border-neutral-200 dark:border-neutral-800">
          <table className="w-full min-w-[40rem] text-sm">
            <thead className="bg-neutral-100 text-left text-xs uppercase tracking-wide text-neutral-500 dark:bg-neutral-900 dark:text-neutral-400">
              <tr>
                <th className="px-3 py-2 font-medium">Task</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium" title="Importance and urgency, 1-4 each">
                  Rating
                </th>
                <th className="px-3 py-2 font-medium">Priority</th>
                <th className="px-3 py-2 font-medium">Project</th>
                <th className="px-3 py-2 font-medium">Due</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-200 bg-white dark:divide-neutral-800 dark:bg-neutral-900">
              {visible.map((task) => (
                <tr key={task.id}>
                  <td className="px-3 py-2">
                    <span className={task.status === "done" ? "line-through opacity-60" : ""}>
                      {task.title}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-neutral-600 dark:text-neutral-400">
                    {STATUS_LABELS[task.status]}
                  </td>
                  <td className="px-3 py-2 text-neutral-600 tabular-nums dark:text-neutral-400">
                    {ratingLabel(task)}
                  </td>
                  <td className="px-3 py-2">
                    {/* Derived from the pair, shown as shorthand only. */}
                    <Badge tone={PRIORITY_TONES[task.priority]}>
                      {PRIORITY_LABELS[task.priority]}
                    </Badge>
                  </td>
                  <td className="px-3 py-2 text-neutral-600 dark:text-neutral-400">
                    {task.project_id ? projectNames.get(task.project_id) ?? "—" : "—"}
                  </td>
                  <td className="px-3 py-2 text-neutral-600 dark:text-neutral-400">
                    {formatDate(task.due_date)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
