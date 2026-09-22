import Link from "next/link";
import { ApiErrorPanel } from "@/components/api-error";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty } from "@/components/ui/empty";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { PROJECT_STATUS_TONES } from "@/lib/tones";

export const dynamic = "force-dynamic";

export default async function ProjectsPage() {
  let projects;
  let habits;
  try {
    [projects, habits] = await Promise.all([api.projects(), api.habits()]);
  } catch (error) {
    return <ApiErrorPanel error={error} />;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Projects and habits</h1>
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          Creating and editing both arrives in W2 — habits have never had an interface
          at all, despite planning and review depending on them.
        </p>
      </div>

      {projects.length === 0 ? (
        <Empty title="No projects yet" />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {projects.map((project) => (
            <Card key={project.id}>
              <CardHeader>
                <CardTitle>
                  <Link href={`/projects/${project.id}`} className="hover:underline">
                    {project.name}
                  </Link>
                </CardTitle>
                <Badge tone={PROJECT_STATUS_TONES[project.status]}>
                  {project.status.replace("_", " ")}
                </Badge>
              </CardHeader>
              <CardBody className="space-y-2">
                <p className="text-sm text-neutral-600 dark:text-neutral-400">
                  {project.description ?? "No description."}
                </p>
                <p className="text-xs text-neutral-500 dark:text-neutral-400">
                  Target: {formatDate(project.target_date)}
                </p>
              </CardBody>
            </Card>
          ))}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Habits</CardTitle>
          <span className="text-xs text-neutral-500 dark:text-neutral-400">
            {habits.length} active
          </span>
        </CardHeader>
        <CardBody>
          {habits.length === 0 ? (
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              No active habits. Until W2 they can only be created by the seed script.
            </p>
          ) : (
            <ul className="space-y-1.5 text-sm">
              {habits.map((habit) => (
                <li key={habit.id} className="flex items-baseline justify-between gap-3">
                  <span>{habit.name}</span>
                  <span className="shrink-0 text-xs text-neutral-500 dark:text-neutral-400">
                    {habit.target_per_period}× {habit.frequency}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
