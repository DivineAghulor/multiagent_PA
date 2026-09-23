"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorText, Select, Textarea } from "@/components/ui/field";
import { actions } from "@/lib/api";
import { cn } from "@/lib/cn";
import { addDays, formatDate, formatTimestamp, mondayOf } from "@/lib/format";
import { useAction } from "@/lib/use-action";
import type { GoalProgress, Week } from "@/lib/types";

const DAY_INITIALS = ["M", "T", "W", "T", "F", "S", "S"];

/**
 * Seven day boxes for a habit goal (FR-16/17). Clicking logs or unlogs that
 * day — idempotent on the server. Days after today are disabled: an unlogged
 * future day hasn't been missed yet.
 */
export function HabitDays({
  habitId,
  weekStart,
  logged,
  today,
}: {
  habitId: number;
  weekStart: string;
  logged: string[];
  today: string | null;
}) {
  const { run, busy, error } = useAction();
  const [pendingDay, setPendingDay] = useState<string | null>(null);
  const days = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));

  const toggle = async (day: string, done: boolean) => {
    setPendingDay(day);
    await run(() =>
      (done ? actions.unlogHabit(habitId, day) : actions.logHabit(habitId, day)).then(() => true),
    );
    setPendingDay(null);
  };

  return (
    <div className="space-y-1">
      <div className="flex gap-1.5">
        {days.map((day, i) => {
          const done = logged.includes(day);
          const future = today !== null && day > today;
          return (
            <button
              key={day}
              type="button"
              disabled={future || busy}
              aria-pressed={done}
              aria-label={`${formatDate(day)}: ${done ? "logged — click to undo" : future ? "in the future" : "not logged — click to log"}`}
              title={`${formatDate(day)}${done ? " — logged" : ""}`}
              onClick={() => toggle(day, done)}
              className={cn(
                "flex h-7 w-7 items-center justify-center rounded-md border text-xs font-medium transition-colors",
                done
                  ? "border-green-600 bg-green-600 text-white hover:bg-green-700"
                  : "border-neutral-300 text-neutral-500 hover:bg-neutral-100 dark:border-neutral-700 dark:text-neutral-400 dark:hover:bg-neutral-800",
                future ? "cursor-not-allowed opacity-40" : "cursor-pointer",
                pendingDay === day ? "animate-pulse" : "",
              )}
            >
              {DAY_INITIALS[i]}
            </button>
          );
        })}
      </div>
      <ErrorText>{error}</ErrorText>
    </div>
  );
}

function weekOptions(weekStart: string, today: string | null): string[] {
  // Later weeks only; start from next week, or from the current week when
  // reviewing further back.
  const thisMonday = today ? mondayOf(today) : null;
  const first = thisMonday && thisMonday > weekStart ? thisMonday : addDays(weekStart, 7);
  return [0, 7, 14, 21].map((d) => addDays(first, d));
}

/** FR-21: carry missed goals into a later week — one at a time or all at
 * once, and only when the user asks. */
export function CarryOver({ week, today }: { week: Week; today: string | null }) {
  const missed = week.goals.filter((g) => g.status === "missed" && g.goal.status !== "carried_over");
  const options = weekOptions(week.week_start, today);
  const [target, setTarget] = useState(options[0]);
  const { run, busy, error } = useAction();

  if (missed.length === 0) return null;

  const carry = (goals: GoalProgress[]) =>
    run(async () => {
      for (const g of goals) await actions.carryOver(g.goal.id, target);
      return true;
    });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Carry over</CardTitle>
        <span className="text-xs text-neutral-500 dark:text-neutral-400">
          {missed.length} missed goal(s); unfinished tasks move with them
        </span>
      </CardHeader>
      <CardBody className="space-y-3">
        <label className="flex items-center gap-2 text-sm">
          Into the week of
          <Select value={target} onChange={(e) => setTarget(e.target.value)} disabled={busy}>
            {options.map((w) => (
              <option key={w} value={w}>
                {formatDate(w)}
              </option>
            ))}
          </Select>
        </label>
        <ul className="space-y-2">
          {missed.map((g) => (
            <li key={g.goal.id} className="flex items-center justify-between gap-3 text-sm">
              <span>{g.goal.description}</span>
              <Button size="sm" disabled={busy} onClick={() => carry([g])}>
                Carry over
              </Button>
            </li>
          ))}
        </ul>
        {missed.length > 1 ? (
          <Button variant="primary" size="sm" disabled={busy} onClick={() => carry(missed)}>
            Carry all {missed.length}
          </Button>
        ) : null}
        <ErrorText>{error}</ErrorText>
      </CardBody>
    </Card>
  );
}

/**
 * FR-19/20/22: the week's review. "Generate" is one model call that writes
 * nothing; the prose can be edited, and "Save" stores exactly that text along
 * with each goal's verdict. The stored review shows the counts it was written
 * against, not today's (§6.7 SCH-2).
 */
export function ReviewPanel({ week, modelReady }: { week: Week; modelReady: boolean }) {
  const [draft, setDraft] = useState<string | null>(null);
  const generate = useAction();
  const save = useAction();

  const runGenerate = async () => {
    const result = await generate.run((signal) => actions.draftReview(week.week_start, signal), {
      refresh: false,
    });
    if (result) setDraft(result.summary);
  };

  const runSave = async (summary: string | null) => {
    const ok = await save.run(() => actions.saveReview(week.week_start, summary));
    if (ok) setDraft(null);
  };

  const stored = week.review;
  const busy = generate.busy || save.busy;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Review</CardTitle>
        {stored && draft === null ? (
          <span className="text-xs text-neutral-500 dark:text-neutral-400">
            Written {formatTimestamp(stored.generated_at)} · against {stored.achieved_count}/
            {stored.measurable_count} goals and {stored.unplanned_count} unplanned
          </span>
        ) : null}
      </CardHeader>
      <CardBody className="space-y-3">
        {draft !== null ? (
          <>
            <Textarea
              rows={8}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              aria-label="Review draft"
              disabled={save.busy}
            />
            <div className="flex flex-wrap gap-2">
              <Button variant="primary" disabled={busy || !draft.trim()} onClick={() => runSave(draft)}>
                {save.busy ? "Saving…" : "Save review"}
              </Button>
              <Button variant="ghost" disabled={busy} onClick={() => setDraft(null)}>
                Discard draft
              </Button>
            </div>
          </>
        ) : stored ? (
          <div className="space-y-3 text-sm whitespace-pre-wrap">{stored.summary}</div>
        ) : (
          <p className="text-sm text-neutral-500 dark:text-neutral-400">
            No review for this week yet. Generating one is a single model call over the facts below;
            nothing is saved until you choose to.
          </p>
        )}

        {draft === null ? (
          <div className="flex flex-wrap items-center gap-2">
            <Button variant={stored ? "secondary" : "primary"} disabled={busy || !modelReady} onClick={runGenerate}>
              {generate.busy ? "Writing…" : stored ? "Regenerate" : "Generate review"}
            </Button>
            {generate.busy ? (
              <Button variant="ghost" onClick={generate.cancel}>
                Cancel
              </Button>
            ) : null}
            {week.measurable_count > 0 ? (
              <Button
                variant="ghost"
                disabled={busy}
                onClick={() => runSave(null)}
                title="Record achieved/missed and per-goal notes, without a narrative"
              >
                Save verdicts only
              </Button>
            ) : null}
            {!modelReady ? (
              <span className="text-xs text-amber-700 dark:text-amber-400">
                No provider key — verdicts can still be saved.
              </span>
            ) : null}
          </div>
        ) : null}
        <ErrorText>{generate.error ?? save.error}</ErrorText>

        <details>
          <summary className="cursor-pointer text-xs text-neutral-500 dark:text-neutral-400">
            The facts the review is written from
          </summary>
          <pre className="mt-2 overflow-x-auto rounded-lg bg-neutral-100 p-3 text-xs leading-relaxed whitespace-pre-wrap text-neutral-700 dark:bg-neutral-950 dark:text-neutral-300">
            {week.facts}
          </pre>
        </details>
      </CardBody>
    </Card>
  );
}
