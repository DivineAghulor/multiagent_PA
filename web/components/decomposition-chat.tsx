"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { ChatInput, ChatLog } from "@/components/chat";
import { DraftLost } from "@/components/draft-lost";
import { DraftOutline, type Exclusions } from "@/components/draft-outline";
import { RatingQueue } from "@/components/rating";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorText, Field, Input, Textarea } from "@/components/ui/field";
import { ApiError, actions, api } from "@/lib/api";
import { streamDecompositionTurn } from "@/lib/sse";
import { errorMessage, isAbort } from "@/lib/use-action";
import type { DecompositionResult, DecompositionSession, TurnProgress } from "@/lib/types";

const TOOL_LABELS: Record<string, string> = {
  add_milestone: "adding a milestone",
  update_milestone: "editing a milestone",
  remove_milestone: "removing a milestone",
  move_milestone: "reordering milestones",
  add_task: "adding a task",
  attach_existing_task: "attaching an existing task",
  update_task: "editing a task",
  remove_task: "removing a task",
  view_draft: "checking the draft",
};

function progressText(p: TurnProgress | null): string {
  if (!p) return "Starting…";
  const tally = `step ${p.step} · ${p.tool_calls} tool call${p.tool_calls === 1 ? "" : "s"}`;
  if (p.phase === "tool" && p.tool) return `${TOOL_LABELS[p.tool] ?? p.tool} — ${tally}`;
  return `Thinking — ${tally}`;
}

/**
 * The decomposition screen (FR-11..FR-15). Turns stream progress, so the long
 * tool-calling loop shows what it's doing and what it has cost so far.
 */
export function DecompositionChat({
  initial,
  modelReady,
}: {
  initial: DecompositionSession;
  modelReady: boolean;
}) {
  const router = useRouter();
  const [session, setSession] = useState(initial);
  const [progress, setProgress] = useState<TurnProgress | null>(null);
  const [busy, setBusy] = useState<"turn" | "confirm" | "cancel" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lost, setLost] = useState(false);
  const [excluded, setExcluded] = useState<Exclusions>({ milestones: new Set(), tasks: new Set() });
  const [confirmed, setConfirmed] = useState<DecompositionResult | null>(null);
  const controller = useRef<AbortController | null>(null);

  const restartHref = session.draft.project_id
    ? `/decompose?project=${session.draft.project_id}`
    : "/decompose";

  const fail = (err: unknown) => {
    if (isAbort(err)) return;
    if (err instanceof ApiError && err.type === "session_expired") setLost(true);
    else setError(errorMessage(err));
  };

  const send = async (text: string): Promise<boolean> => {
    const ctrl = new AbortController();
    controller.current = ctrl;
    setBusy("turn");
    setProgress(null);
    setError(null);
    try {
      // Unticked items are dropped from the draft before this turn, so the
      // model works on what the user kept; after it, nothing is unticked.
      const next = await streamDecompositionTurn(session.session_id, text, {
        onProgress: setProgress,
        signal: ctrl.signal,
        exclude: { milestone_refs: [...excluded.milestones], task_refs: [...excluded.tasks] },
      });
      setSession(next);
      setExcluded({ milestones: new Set(), tasks: new Set() });
      return true;
    } catch (err) {
      if (isAbort(err)) {
        // A turn stopped mid-way is never committed, but one that finished as
        // Stop was pressed may have been: re-read rather than assume.
        setError("Stopped.");
        api.decompositionSession(session.session_id).then(setSession, fail);
      } else fail(err);
      return false;
    } finally {
      controller.current = null;
      setBusy(null);
      setProgress(null);
    }
  };

  const toggle = (kind: "milestones" | "tasks", ref: string) =>
    setExcluded((ex) => {
      const next = new Set(ex[kind]);
      if (next.has(ref)) next.delete(ref);
      else next.add(ref);
      return { ...ex, [kind]: next };
    });

  const confirm = async () => {
    setBusy("confirm");
    setError(null);
    try {
      const result = await actions.confirmDecomposition(session.session_id, {
        milestone_refs: [...excluded.milestones],
        task_refs: [...excluded.tasks],
      });
      if (result.new_tasks.length > 0) {
        setConfirmed(result); // rate the new tasks before leaving
        setBusy(null);
      } else {
        router.push(`/projects/${result.project.id}`);
        router.refresh();
      }
    } catch (err) {
      // The "adds nothing" / "milestones without tasks" guards land here with
      // their own message; both are fixed by another turn (FR-14).
      fail(err);
      setBusy(null);
    }
  };

  const discard = async () => {
    setBusy("cancel");
    try {
      await actions.cancelDecomposition(session.session_id);
    } catch {
      // Already gone is fine.
    }
    router.push(session.draft.project_id ? `/projects/${session.draft.project_id}` : "/projects");
  };

  if (lost) return <DraftLost what="project breakdown" restartHref={restartHref} />;

  if (confirmed) {
    const done = () => {
      router.push(`/projects/${confirmed.project.id}`);
      router.refresh();
    };
    return (
      <Card>
        <CardHeader>
          <CardTitle>Saved: {confirmed.project.name}</CardTitle>
          <span className="text-xs text-neutral-500 dark:text-neutral-400">
            {confirmed.milestones.length} milestone(s) · {confirmed.new_tasks.length} new task(s)
          </span>
        </CardHeader>
        <CardBody className="space-y-4">
          <p className="text-sm text-neutral-600 dark:text-neutral-400">
            The new tasks start unrated. Rate them now, or skip and do it later from Tasks.
          </p>
          <RatingQueue tasks={confirmed.new_tasks} onEmpty={done} />
          <Button variant="ghost" onClick={done}>
            Go to the project
          </Button>
        </CardBody>
      </Card>
    );
  }

  const { draft, last_turn } = session;
  const newMilestones = draft.milestones.filter((m) => m.existing_id === null).length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Break down: {draft.project_name}</h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400">
            {draft.project_id ? "Existing project" : "New project — created when you confirm"}. A turn
            makes many model calls; nothing is saved until you confirm.
          </p>
        </div>
        <Button variant="ghost" onClick={discard} disabled={busy !== null}>
          Discard
        </Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Conversation</CardTitle>
            {last_turn ? (
              <span
                className="text-xs text-neutral-500 tabular-nums dark:text-neutral-400"
                title="What the last turn cost"
              >
                last turn: {last_turn.steps} model call{last_turn.steps === 1 ? "" : "s"},{" "}
                {last_turn.tool_calls} tool call{last_turn.tool_calls === 1 ? "" : "s"}
              </span>
            ) : null}
          </CardHeader>
          <CardBody className="space-y-4">
            <ChatLog
              messages={session.messages}
              pending={busy === "turn" ? progressText(progress) : null}
              empty={
                draft.project_id
                  ? "Say what to add: the next phase, a timeline, what's missing."
                  : "Say what the project is for and any timeline — the assistant drafts milestones and tasks."
              }
            />
            {last_turn?.hit_limit && busy !== "turn" ? (
              <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
                The last turn hit the step limit before finishing. The draft so far is kept — say
                &ldquo;continue&rdquo; or tell it what to change.
              </p>
            ) : null}
            <ChatInput
              onSend={send}
              onCancel={() => controller.current?.abort()}
              busy={busy === "turn"}
              disabled={!modelReady || busy === "confirm"}
              placeholder={modelReady ? "e.g. Launch in 6 weeks; I already have a mic" : "No provider key configured"}
            />
            <ErrorText>{error}</ErrorText>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Draft</CardTitle>
            <span className="text-xs text-neutral-500 dark:text-neutral-400">
              {newMilestones} new milestone(s) · {draft.new_task_count} new task(s)
            </span>
          </CardHeader>
          <CardBody className="space-y-4">
            <DraftOutline draft={draft} excluded={excluded} onToggle={toggle} disabled={busy !== null} />
            <Button
              variant="primary"
              onClick={confirm}
              disabled={busy !== null || draft.milestones.length === 0}
            >
              {busy === "confirm" ? "Saving…" : "Confirm breakdown"}
            </Button>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

/** Start a draft for a project that already exists (FR-11). */
export function StartExistingDecomposition({
  projectId,
  projectName,
  modelReady,
}: {
  projectId: number;
  projectName: string;
  modelReady: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const session = await actions.startDecomposition({ project_id: projectId });
      router.replace(`/decompose?session=${session.session_id}`);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <h1 className="text-lg font-semibold tracking-tight">Break down: {projectName}</h1>
      <p className="text-sm text-neutral-500 dark:text-neutral-400">
        The assistant sees the project&apos;s existing milestones and its unassigned tasks, and adds
        around them. Existing milestones can gain tasks but aren&apos;t renamed or removed.
      </p>
      <Button variant="primary" onClick={start} disabled={busy || !modelReady}>
        {busy ? "Opening…" : "Start breakdown"}
      </Button>
      {!modelReady ? (
        <p className="text-xs text-amber-700 dark:text-amber-400">No provider key configured.</p>
      ) : null}
      <ErrorText>{error}</ErrorText>
    </div>
  );
}

/** Start a draft for a brand-new project; it's only created on confirm. */
export function StartNewDecomposition({ modelReady }: { modelReady: boolean }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const session = await actions.startDecomposition({
        name: name.trim(),
        description: description.trim() || null,
      });
      router.replace(`/decompose?session=${session.session_id}`);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  };

  return (
    <form
      className="max-w-xl space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        start();
      }}
    >
      <h1 className="text-lg font-semibold tracking-tight">Break down a new project</h1>
      <p className="text-sm text-neutral-500 dark:text-neutral-400">
        Nothing is created until you confirm the breakdown. To extend an existing project, open it
        from Projects instead.
      </p>
      <Field label="Project name">
        <Input value={name} onChange={(e) => setName(e.target.value)} required maxLength={300} autoFocus />
      </Field>
      <Field label="What is it for?" hint="The assistant reads this; say what done looks like.">
        <Textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
      </Field>
      <Button type="submit" variant="primary" disabled={busy || !name.trim() || !modelReady}>
        {busy ? "Opening…" : "Start breakdown"}
      </Button>
      {!modelReady ? (
        <p className="text-xs text-amber-700 dark:text-amber-400">No provider key configured.</p>
      ) : null}
      <ErrorText>{error}</ErrorText>
    </form>
  );
}
