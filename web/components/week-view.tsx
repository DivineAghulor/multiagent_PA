import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty } from "@/components/ui/empty";
import { Progress } from "@/components/ui/progress";
import { addDays, formatDate, formatTimestamp } from "@/lib/format";
import type { GoalProgress, Task, Week } from "@/lib/types";

const DAY_INITIALS = ["M", "T", "W", "T", "F", "S", "S"];

/**
 * Seven boxes for a habit goal. Days after today are dimmed because they
 * haven't happened yet — an unlogged future day is not a missed one (FR-16).
 * Nothing here is interactive yet: ticking is W4.
 */
function HabitWeek({ weekStart, logged, today }: { weekStart: string; logged: string[]; today: string | null }) {
  const days = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));
  return (
    <div className="flex gap-1.5">
      {days.map((day, i) => {
        const done = logged.includes(day);
        const future = today !== null && day > today;
        return (
          <span
            key={day}
            title={`${formatDate(day)}${done ? " — logged" : ""}`}
            className={[
              "flex h-7 w-7 items-center justify-center rounded-md border text-xs font-medium",
              done
                ? "border-green-600 bg-green-600 text-white"
                : "border-neutral-300 text-neutral-500 dark:border-neutral-700 dark:text-neutral-400",
              future ? "opacity-40" : "",
            ].join(" ")}
          >
            {DAY_INITIALS[i]}
          </span>
        );
      })}
    </div>
  );
}

function TaskLine({ task }: { task: Task }) {
  const done = task.status === "done";
  return (
    <li className="flex items-baseline gap-2 text-sm">
      <span
        aria-hidden
        className={
          done
            ? "text-green-600 dark:text-green-500"
            : "text-neutral-300 dark:text-neutral-600"
        }
      >
        {done ? "\u2713" : "\u25cb"}
      </span>
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
        {status === null ? (
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

        {kind === "habit" ? (
          <HabitWeek weekStart={weekStart} logged={progress.done} today={today} />
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

export function WeekView({ week, today }: { week: Week; today: string | null }) {
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

      {week.review ? (
        <Card>
          <CardHeader>
            <CardTitle>Review</CardTitle>
            <span className="text-xs text-neutral-500 dark:text-neutral-400">
              Written {formatTimestamp(week.review.generated_at)} · against{" "}
              {week.review.achieved_count}/{week.review.measurable_count} goals and{" "}
              {week.review.unplanned_count} unplanned
            </span>
          </CardHeader>
          <CardBody>
            {/* The stored counts above are the ones the prose was written
                against, not today's — see requirements §6.7 SCH-2. */}
            <div className="space-y-3 text-sm whitespace-pre-wrap">{week.review.summary}</div>
          </CardBody>
        </Card>
      ) : null}

      {week.goals.length === 0 ? (
        <Empty
          title="No goals set for this week"
          hint="Weekly planning turns your backlog into goals — that conversation arrives in W3."
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
    </div>
  );
}
