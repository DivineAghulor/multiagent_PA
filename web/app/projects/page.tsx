import Link from "next/link";
import { ApiErrorPanel } from "@/components/api-error";
import { HabitManager } from "@/components/habit-manager";
import { NewProjectForm } from "@/components/project-forms";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty } from "@/components/ui/empty";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { PROJECT_STATUS_TONES } from "@/lib/tones";
import type { Project } from "@/lib/types";

export const dynamic = "force-dynamic";

function ProjectCard({ project }: { project: Project }) {
  return (
    <Card className={project.status === "archived" ? "opacity-70" : undefined}>
      <CardHeader>
        <CardTitle>
          <Link href={`/projects/${project.id}`} className="hover:underline">
            {project.name}
          </Link>
        </CardTitle>
        <Badge tone={PROJECT_STATUS_TONES[project.status]}>{project.status.replace("_", " ")}</Badge>
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
  );
}

export default async function ProjectsPage() {
  let projects;
  let habits;
  try {
    [projects, habits] = await Promise.all([api.projects(), api.habits({ active_only: false })]);
  } catch (error) {
    return <ApiErrorPanel error={error} />;
  }

  const current = projects.filter((p) => p.status !== "archived");
  const archived = projects.filter((p) => p.status === "archived");

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Projects and habits</h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400">
            Planning draws on active projects and habits; archived and inactive ones keep their
            history.
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <NewProjectForm />
        <Link href="/decompose" className="text-sm text-neutral-600 hover:underline dark:text-neutral-400">
          …or describe a new project and let the assistant break it down
        </Link>
      </div>

      {current.length === 0 ? (
        <Empty title="No projects yet" hint="Create one, then break it down with the assistant." />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {current.map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))}
        </div>
      )}

      {archived.length > 0 ? (
        <details className="group">
          <summary className="cursor-pointer text-sm text-neutral-500 dark:text-neutral-400">
            Archived projects ({archived.length})
          </summary>
          <div className="mt-3 grid gap-4 md:grid-cols-2">
            {archived.map((project) => (
              <ProjectCard key={project.id} project={project} />
            ))}
          </div>
        </details>
      ) : null}

      <HabitManager habits={habits} />
    </div>
  );
}
