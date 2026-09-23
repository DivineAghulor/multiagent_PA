import Link from "next/link";
import { TaskCheckbox } from "@/components/task-actions";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty } from "@/components/ui/empty";
import { Progress } from "@/components/ui/progress";
import { CarryOver, HabitDays, ReviewPanel } from "@/components/week-controls";
import { addDays, formatDate } from "@/lib/format";
import type { GoalProgress, Task, Week } from "@/lib/types";

/** A task with its tick box: ticking completes it, unticking reopens it (FR-17). */
function TaskLine({ task }: { task: Task }) {
  const done = task.status === "done";
  return (
    <li className="flex items-center gap-2 text-sm">
      <TaskCheckbox task={task} />
      <span className={done ? "text-neutral-500 line-through dark:text-neutral-500" : ""}>
        {task.title}
      </span>
    </li>
  );
}

function GoalCard({ progress, weekStart, today }: { progress: GoalProgress; weekStart: string; today: string | null }) {
  const { goal, kind, achieved, status } = progress;
  return (
    <Card>
      <CardHeader>
        <CardTitle>{goal.description}</CardTitle>
        {goal.status === "carried_over" ? (
          <Badge tone="blue" title="Copied into a later week with its unfinished tasks">
            Carried over
          </Badge>
        ) : status === null ? (
          <Badge tone="neutral" title="No target and no tasks attached, so there is nothing to measure">
            Not measurable
          </Badge>
        ) : (
          <Badge tone={achieved ? "green" : "amber"}>{achieved ? "Achieved" : "Missed"}</Badge>
        )}
      </CardHeader>
      <CardBody className="space-y-3">
        <p className="text-sm text-neutral-600 dark:text-neutral-400">{progress.headline}</p>
        <Progress value={progress.completed} max={progress.target} />

        {kind === "habit" && goal.habit_id !== null ? (
          <HabitDays habitId={goal.habit_id} weekStart={weekStart} logged={progress.done} today={today} />
        ) : null}

        {progress.tasks.length > 0 ? (
          <ul className="space-y-1">
            {progress.tasks.map((task) => (
              <TaskLine key={task.id} task={task} />
            ))}
          </ul>
        ) : null}
      </CardBody>
    </Card>
  );
}

export function WeekView({
  week,
  today,
  modelReady,
}: {
  week: Week;
  today: string | null;
  modelReady: boolean;
}) {
  const previous = addDays(week.week_start, -7);
  const next = addDays(week.week_start, 7);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">
            Week of {formatDate(week.week_start)}
          </h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400">
            {week.achieved_count} of {week.measurable_count} measurable goals achieved
          </p>
        </div>
        <div className="flex gap-2 text-sm">
          <Link
            href={`/week/${previous}`}
            className="rounded-md border border-neutral-300 px-2.5 py-1 hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
          >
            ← Previous
          </Link>
          <Link
            href={`/week/${next}`}
            className="rounded-md border border-neutral-300 px-2.5 py-1 hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
          >
            Next →
          </Link>
        </div>
      </div>

      {week.goals.length === 0 ? (
        <Empty
          title="No goals set for this week"
          hint="Weekly planning turns your backlog into goals — open Planning to start."
        />
      ) : (
        <div className="space-y-4">
          {week.goals.map((progress) => (
            <GoalCard
              key={progress.goal.id}
              progress={progress}
              weekStart={week.week_start}
              today={today}
            />
          ))}
        </div>
      )}

      <CarryOver week={week} today={today} />

      <Card>
        <CardHeader>
          <CardTitle>Done outside the plan</CardTitle>
          <span className="text-xs text-neutral-500 dark:text-neutral-400">
            {week.unplanned_done.length} task(s)
          </span>
        </CardHeader>
        <CardBody>
          {week.unplanned_done.length === 0 ? (
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              Nothing completed this week that wasn&apos;t part of a goal.
            </p>
          ) : (
            <ul className="space-y-1">
              {week.unplanned_done.map((task) => (
                <TaskLine key={task.id} task={task} />
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      <ReviewPanel week={week} modelReady={modelReady} />
    </div>
  );
}
