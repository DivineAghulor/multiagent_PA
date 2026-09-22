import { ApiErrorPanel } from "@/components/api-error";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty } from "@/components/ui/empty";
import { api } from "@/lib/api";
import { formatDate, ratingLabel } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function PlanningPage() {
  let context;
  try {
    context = await api.planningContext();
  } catch (error) {
    return <ApiErrorPanel error={error} />;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">
          Planning week of {formatDate(context.week_start)}
        </h1>
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          Everything the planning model would be shown. Reading it costs nothing — the
          conversation that turns it into goals arrives in W3.
        </p>
      </div>

      {context.existing_goals.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Goals already set for this week</CardTitle>
            <Badge tone="blue">{context.existing_goals.length}</Badge>
          </CardHeader>
          <CardBody>
            <ul className="space-y-1 text-sm">
              {context.existing_goals.map((goal) => (
                <li key={goal.id}>{goal.description}</li>
              ))}
            </ul>
          </CardBody>
        </Card>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Backlog</CardTitle>
            <span className="text-xs text-neutral-500 dark:text-neutral-400">
              {context.backlog.length} unattached
            </span>
          </CardHeader>
          <CardBody>
            {context.backlog.length === 0 ? (
              <p className="text-sm text-neutral-500 dark:text-neutral-400">
                Nothing waiting. Tasks already attached to a goal are excluded.
              </p>
            ) : (
              <ul className="space-y-1.5 text-sm">
                {context.backlog.map((task) => (
                  <li key={task.id} className="flex items-baseline justify-between gap-3">
                    <span>{task.title}</span>
                    <span className="shrink-0 text-xs text-neutral-500 tabular-nums dark:text-neutral-400">
                      {ratingLabel(task)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Active projects and habits</CardTitle>
          </CardHeader>
          <CardBody className="space-y-4">
            <div>
              <p className="mb-1.5 text-xs uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                Projects
              </p>
              {context.projects.length === 0 ? (
                <p className="text-sm text-neutral-500 dark:text-neutral-400">None active.</p>
              ) : (
                <ul className="space-y-1 text-sm">
                  {context.projects.map((project) => (
                    <li key={project.id}>{project.name}</li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <p className="mb-1.5 text-xs uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                Habits
              </p>
              {context.habits.length === 0 ? (
                <p className="text-sm text-neutral-500 dark:text-neutral-400">None active.</p>
              ) : (
                <ul className="space-y-1 text-sm">
                  {context.habits.map((habit) => (
                    <li key={habit.id}>
                      {habit.name}{" "}
                      <span className="text-neutral-500 dark:text-neutral-400">
                        ({habit.target_per_period}× {habit.frequency})
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>The prompt context, as the model sees it</CardTitle>
        </CardHeader>
        <CardBody>
          {context.rendered.trim() === "" ? (
            <Empty title="Nothing to plan with yet" />
          ) : (
            <pre className="overflow-x-auto text-xs leading-relaxed whitespace-pre-wrap text-neutral-700 dark:text-neutral-300">
              {context.rendered}
            </pre>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
