import { ApiErrorPanel } from "@/components/api-error";
import { CaptureBox } from "@/components/capture-box";
import { TaskTable } from "@/components/task-table";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function TasksPage() {
  let tasks;
  let projects;
  let health;
  try {
    // Projects come along so the table can show project names without a lookup
    // endpoint per row; health says whether capture can call the model.
    [tasks, projects, health] = await Promise.all([api.tasks(), api.projects(), api.health()]);
  } catch (error) {
    return <ApiErrorPanel error={error} />;
  }

  const unrated = tasks.filter(
    (t) => (t.importance === null || t.urgency === null) && t.status !== "done" && t.status !== "cancelled",
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Tasks</h1>
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          Rated by importance and urgency; the priority badge is shorthand for that pair.
        </p>
      </div>
      <CaptureBox modelReady={health.provider_key_configured} unrated={unrated} />
      <TaskTable tasks={tasks} projects={projects} />
    </div>
  );
}
