import { ApiErrorPanel } from "@/components/api-error";
import { TaskTable } from "@/components/task-table";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function TasksPage() {
  let tasks;
  let projects;
  try {
    // Projects come along so the table can show project names without a lookup
    // endpoint per row.
    [tasks, projects] = await Promise.all([api.tasks(), api.projects()]);
  } catch (error) {
    return <ApiErrorPanel error={error} />;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Tasks</h1>
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          Rated by importance and urgency; the priority badge is shorthand for that pair.
        </p>
      </div>
      <TaskTable tasks={tasks} projects={projects} />
    </div>
  );
}
