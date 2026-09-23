"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { ErrorText, Field, Input, Select, Textarea } from "@/components/ui/field";
import { actions, type HabitEdit } from "@/lib/api";
import { useAction } from "@/lib/use-action";
import type { Habit, HabitFrequency } from "@/lib/types";

const FREQUENCIES: HabitFrequency[] = ["daily", "weekdays", "weekly", "custom"];

interface Draft {
  name: string;
  description: string;
  frequency: HabitFrequency;
  target: number;
}

const blank: Draft = { name: "", description: "", frequency: "daily", target: 1 };

function HabitFields({ draft, onChange }: { draft: Draft; onChange: (d: Draft) => void }) {
  return (
    <>
      <Field label="Name">
        <Input
          value={draft.name}
          onChange={(e) => onChange({ ...draft, name: e.target.value })}
          required
          maxLength={300}
          autoFocus
        />
      </Field>
      <Field label="Description">
        <Textarea
          rows={2}
          value={draft.description}
          onChange={(e) => onChange({ ...draft, description: e.target.value })}
        />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Frequency">
          <Select
            className="w-full"
            value={draft.frequency}
            onChange={(e) => onChange({ ...draft, frequency: e.target.value as HabitFrequency })}
          >
            {FREQUENCIES.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Times per period" hint="Planning uses this as the weekly target.">
          <Input
            type="number"
            min={1}
            max={100}
            value={draft.target}
            onChange={(e) => onChange({ ...draft, target: Math.max(1, Number(e.target.value) || 1) })}
          />
        </Field>
      </div>
    </>
  );
}

function HabitRow({ habit }: { habit: Habit }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Draft>(blank);
  const save = useAction();
  const toggle = useAction();

  const open = () => {
    setDraft({
      name: habit.name,
      description: habit.description ?? "",
      frequency: habit.frequency,
      target: habit.target_per_period,
    });
    setEditing(true);
  };

  const submit = async () => {
    const edit: HabitEdit = {};
    if (draft.name.trim() !== habit.name) edit.name = draft.name.trim();
    if ((draft.description.trim() || null) !== habit.description) edit.description = draft.description.trim() || null;
    if (draft.frequency !== habit.frequency) edit.frequency = draft.frequency;
    if (draft.target !== habit.target_per_period) edit.target_per_period = draft.target;
    if (Object.keys(edit).length === 0) return setEditing(false);
    const ok = await save.run(() => actions.updateHabit(habit.id, edit));
    if (ok) setEditing(false);
  };

  return (
    <li className="flex flex-wrap items-center justify-between gap-2 py-2">
      <div className={habit.active ? "" : "opacity-60"}>
        <span className="text-sm">{habit.name}</span>{" "}
        <span className="text-xs text-neutral-500 dark:text-neutral-400">
          {habit.target_per_period}× {habit.frequency}
        </span>
        {!habit.active ? (
          <Badge className="ml-2" tone="neutral">
            inactive
          </Badge>
        ) : null}
      </div>
      <div className="flex items-center gap-1">
        <ErrorText>{toggle.error}</ErrorText>
        <Button variant="ghost" size="sm" onClick={open}>
          Edit
        </Button>
        {habit.active ? (
          <Button
            variant="ghost"
            size="sm"
            disabled={toggle.busy}
            onClick={() => toggle.run(() => actions.deactivateHabit(habit.id))}
          >
            Deactivate
          </Button>
        ) : (
          <Button
            variant="ghost"
            size="sm"
            disabled={toggle.busy}
            onClick={() => toggle.run(() => actions.updateHabit(habit.id, { active: true }))}
          >
            Reactivate
          </Button>
        )}
      </div>

      <Dialog open={editing} onClose={() => setEditing(false)} title="Edit habit">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <HabitFields draft={draft} onChange={setDraft} />
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            Past logs are kept whatever you change here.
          </p>
          <ErrorText>{save.error}</ErrorText>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setEditing(false)} disabled={save.busy}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={save.busy || !draft.name.trim()}>
              {save.busy ? "Saving…" : "Save"}
            </Button>
          </div>
        </form>
      </Dialog>
    </li>
  );
}

/**
 * FR-24: the first interface habits have ever had. Planning and review both
 * depend on habits existing, which until now meant the seed script.
 */
export function HabitManager({ habits }: { habits: Habit[] }) {
  const [creating, setCreating] = useState(false);
  const [showInactive, setShowInactive] = useState(false);
  const [draft, setDraft] = useState<Draft>(blank);
  const create = useAction();

  const active = habits.filter((h) => h.active);
  const visible = showInactive ? habits : active;

  const submit = async () => {
    const ok = await create.run(() =>
      actions.createHabit({
        name: draft.name.trim(),
        description: draft.description.trim() || null,
        frequency: draft.frequency,
        target_per_period: draft.target,
      }),
    );
    if (ok) {
      setDraft(blank);
      setCreating(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Habits</CardTitle>
        <div className="flex items-center gap-3">
          {habits.length > active.length ? (
            <label className="flex items-center gap-1.5 text-xs text-neutral-500 dark:text-neutral-400">
              <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
              Show inactive ({habits.length - active.length})
            </label>
          ) : null}
          <Button size="sm" onClick={() => setCreating(true)}>
            New habit
          </Button>
        </div>
      </CardHeader>
      <CardBody>
        {visible.length === 0 ? (
          <p className="text-sm text-neutral-500 dark:text-neutral-400">
            No active habits. Add one and weekly planning can set goals against it.
          </p>
        ) : (
          <ul className="divide-y divide-neutral-200 dark:divide-neutral-800">
            {visible.map((habit) => (
              <HabitRow key={habit.id} habit={habit} />
            ))}
          </ul>
        )}
      </CardBody>

      <Dialog open={creating} onClose={() => setCreating(false)} title="New habit">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <HabitFields draft={draft} onChange={setDraft} />
          <ErrorText>{create.error}</ErrorText>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setCreating(false)} disabled={create.busy}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={create.busy || !draft.name.trim()}>
              {create.busy ? "Creating…" : "Create habit"}
            </Button>
          </div>
        </form>
      </Dialog>
    </Card>
  );
}
