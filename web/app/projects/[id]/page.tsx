import Link from "next/link";
import { ApiErrorPanel } from "@/components/api-error";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty } from "@/components/ui/empty";
import { api } from "@/lib/api";
import { STATUS_LABELS, formatDate, ratingLabel } from "@/lib/format";
import { PROJECT_STATUS_TONES } from "@/lib/tones";
import type { Milestone, Task } from "@/lib/types";

export const dynamic = "force-dynamic";

function TaskRow({ task }: { task: Task }) {
  return (
    <li className="flex items-baseline justify-between gap-3 text-sm">
      <span className={task.status === "done" ? "line-through opacity-60" : ""}>
        {task.title}
      </span>
      <span className="shrink-0 text-xs text-neutral-500 dark:text-neutral-400">
        {STATUS_LABELS[task.status]} · {ratingLabel(task)}
      </span>
    </li>
  );
}

export default async function ProjectDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let project;
  try {
    project = await api.project(Number(id));
  } catch (error) {
    return <ApiErrorPanel error={error} />;
  }

  // Tasks arrive flat with a milestone_id; grouping them here keeps the API
  // from having to nest them.
  const byMilestone = new Map<number, Task[]>();
  const unassigned: Task[] = [];
  for (const task of project.tasks) {
    if (task.milestone_id === null) {
      unassigned.push(task);
    } else {
      byMilestone.set(task.milestone_id, [...(byMilestone.get(task.milestone_id) ?? []), task]);
    }
  }

  const milestoneCard = (milestone: Milestone) => {
    const tasks = byMilestone.get(milestone.id) ?? [];
    const done = tasks.filter((t) => t.status === "done").length;
    return (
      <Card key={milestone.id}>
        <CardHeader>
          <CardTitle>
            {milestone.position !== null ? `${milestone.position}. ` : ""}
            {milestone.name}
          </CardTitle>
          <span className="text-xs text-neutral-500 dark:text-neutral-400">
            {milestone.status.replace("_", " ")} · {done}/{tasks.length} done · due{" "}
            {formatDate(milestone.due_date)}
          </span>
        </CardHeader>
        <CardBody>
          {tasks.length === 0 ? (
            <p className="text-sm text-neutral-500 dark:text-neutral-400">No tasks yet.</p>
          ) : (
            <ul className="space-y-1.5">
              {tasks.map((task) => (
                <TaskRow key={task.id} task={task} />
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
    );
  };

  return (
    <div className="space-y-6">
      <div>
        <Link
          href="/projects"
          className="text-xs text-neutral-500 hover:underline dark:text-neutral-400"
        >
          ← All projects
        </Link>
        <div className="mt-1 flex flex-wrap items-center gap-3">
          <h1 className="text-lg font-semibold tracking-tight">{project.name}</h1>
          <Badge tone={PROJECT_STATUS_TONES[project.status]}>
            {project.status.replace("_", " ")}
          </Badge>
        </div>
        <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
          {project.description ?? "No description."}
        </p>
        <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
          Target: {formatDate(project.target_date)}
        </p>
      </div>

      {project.milestones.length === 0 ? (
        <Empty
          title="Not broken down yet"
          hint="The decomposition conversation that produces milestones arrives in W4."
        />
      ) : (
        <div className="space-y-4">{project.milestones.map(milestoneCard)}</div>
      )}

      {unassigned.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Not under a milestone</CardTitle>
            <span className="text-xs text-neutral-500 dark:text-neutral-400">
              {unassigned.length} task(s)
            </span>
          </CardHeader>
          <CardBody>
            <ul className="space-y-1.5">
              {unassigned.map((task) => (
                <TaskRow key={task.id} task={task} />
              ))}
            </ul>
          </CardBody>
        </Card>
      ) : null}
    </div>
  );
}
