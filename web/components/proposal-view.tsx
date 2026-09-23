"use client";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/field";
import type { Proposal, ProposalGoal } from "@/lib/types";

/** The user's changes to one proposed goal before confirming. */
export interface GoalEdit {
  include: boolean;
  description: string;
  target: number | null;
}

export function editsFor(proposal: Proposal | null): GoalEdit[] {
  return (proposal?.goals ?? []).map((g) => ({
    include: true,
    description: g.description,
    target: g.target_count,
  }));
}

function Links({ goal }: { goal: ProposalGoal }) {
  return (
    <>
      {goal.project_name ? <Badge tone="blue">project: {goal.project_name}</Badge> : null}
      {goal.habit_name ? <Badge tone="green">habit: {goal.habit_name}</Badge> : null}
    </>
  );
}

function targetLabel(goal: ProposalGoal, target: number): string {
  return `target ${target}${goal.habit_name ? "×" : goal.tasks.length ? ` of ${goal.tasks.length}` : ""}`;
}

/**
 * FR-8: the plan as structure, not prose. Every ID here already passed
 * sanitize_proposal on the server, so each name is a real row.
 *
 * With `edits`, each goal can be unticked, reworded and re-targeted before
 * confirming; what it links to (project, habit, tasks) stays as proposed —
 * changing that is what another turn is for.
 */
export function ProposalView({
  proposal,
  edits,
  onEdit,
  disabled,
}: {
  proposal: Proposal;
  edits?: GoalEdit[];
  onEdit?: (index: number, edit: GoalEdit) => void;
  disabled?: boolean;
}) {
  if (proposal.goals.length === 0) {
    return (
      <p className="text-sm text-neutral-500 dark:text-neutral-400">
        No goals proposed yet — answer the assistant&apos;s question or say what you want from the week.
      </p>
    );
  }
  return (
    <ol className="space-y-3">
      {proposal.goals.map((goal, i) => {
        const edit = edits?.[i];
        const out = edit ? !edit.include : false;
        const maxTarget = goal.habit_name ? 100 : goal.tasks.length || 100;
        return (
          <li
            key={i}
            className="rounded-lg border border-neutral-200 px-4 py-3 dark:border-neutral-800"
          >
            {edit && onEdit ? (
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    className="h-4 w-4 shrink-0"
                    checked={edit.include}
                    disabled={disabled}
                    aria-label={`Include goal ${i + 1}`}
                    onChange={(e) => onEdit(i, { ...edit, include: e.target.checked })}
                  />
                  <Input
                    value={edit.description}
                    disabled={disabled || out}
                    aria-label={`Goal ${i + 1}`}
                    maxLength={300}
                    onChange={(e) => onEdit(i, { ...edit, description: e.target.value })}
                  />
                </div>
                <div className={`flex flex-wrap items-center gap-2 pl-6 ${out ? "opacity-50" : ""}`}>
                  <Links goal={goal} />
                  <label className="flex items-center gap-1 text-xs text-neutral-500 dark:text-neutral-400">
                    target
                    <Input
                      type="number"
                      min={1}
                      max={maxTarget}
                      className="w-16 py-0.5 text-xs"
                      value={edit.target ?? ""}
                      placeholder="none"
                      disabled={disabled || out}
                      aria-label={`Target for goal ${i + 1}`}
                      onChange={(e) => {
                        const n = Number(e.target.value);
                        onEdit(i, { ...edit, target: e.target.value === "" || n < 1 ? null : Math.min(n, maxTarget) });
                      }}
                    />
                    {goal.habit_name ? "×" : goal.tasks.length ? `of ${goal.tasks.length}` : ""}
                  </label>
                </div>
              </div>
            ) : (
              <div className="flex flex-wrap items-baseline gap-2">
                <span className="text-sm font-medium">
                  {i + 1}. {goal.description}
                </span>
                <Links goal={goal} />
                {goal.target_count !== null ? (
                  <Badge tone="neutral">{targetLabel(goal, goal.target_count)}</Badge>
                ) : null}
              </div>
            )}
            {goal.tasks.length > 0 ? (
              <ul
                className={`mt-2 space-y-0.5 text-sm text-neutral-600 dark:text-neutral-400 ${edit ? "pl-6" : ""} ${out ? "opacity-50" : ""}`}
              >
                {goal.tasks.map((task) => (
                  <li key={task.id}>· {task.title}</li>
                ))}
              </ul>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

/** S-6: what the server had to fix in the model's output, shown rather than hidden. */
export function Warnings({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) return null;
  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 dark:border-amber-900 dark:bg-amber-950/40">
      <p className="text-xs font-semibold text-amber-900 dark:text-amber-200">
        Corrected in the assistant&apos;s proposal
      </p>
      <ul className="mt-1 space-y-0.5 text-xs text-amber-800 dark:text-amber-300">
        {warnings.map((w, i) => (
          <li key={i}>{w}</li>
        ))}
      </ul>
    </div>
  );
}
