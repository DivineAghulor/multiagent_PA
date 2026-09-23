"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { ChatInput, ChatLog } from "@/components/chat";
import { DraftLost } from "@/components/draft-lost";
import { type GoalEdit, ProposalView, Warnings, editsFor } from "@/components/proposal-view";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorText } from "@/components/ui/field";
import { ApiError, actions } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { errorMessage, isAbort } from "@/lib/use-action";
import type { PlanningSession } from "@/lib/types";

/**
 * The planning conversation (FR-6..FR-9). Each turn returns the whole session,
 * so this component just replaces its copy. Nothing is written until Confirm.
 */
export function PlanningChat({
  initial,
  modelReady,
}: {
  initial: PlanningSession;
  modelReady: boolean;
}) {
  const router = useRouter();
  const [session, setSession] = useState(initial);
  // Reset whenever a turn brings a new proposal: edits apply to the plan the
  // user was looking at, not to one that replaced it.
  const [edits, setEdits] = useState<GoalEdit[]>(() => editsFor(initial.proposal));
  const [busy, setBusy] = useState<"turn" | "confirm" | "cancel" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lost, setLost] = useState(false);
  const controller = useRef<AbortController | null>(null);

  const fail = (err: unknown) => {
    if (isAbort(err)) return;
    if (err instanceof ApiError && err.type === "session_expired") setLost(true);
    else setError(errorMessage(err));
  };

  const send = async (text: string): Promise<boolean> => {
    const ctrl = new AbortController();
    controller.current = ctrl;
    setBusy("turn");
    setError(null);
    try {
      const next = await actions.planningMessage(session.session_id, text, ctrl.signal);
      setSession(next);
      setEdits(editsFor(next.proposal));
      return true;
    } catch (err) {
      fail(err);
      return false;
    } finally {
      controller.current = null;
      setBusy(null);
    }
  };

  const confirm = async () => {
    setBusy("confirm");
    setError(null);
    try {
      const proposed = session.proposal?.goals ?? [];
      const untouched = edits.every(
        (e, i) => e.include && e.description === proposed[i].description && e.target === proposed[i].target_count,
      );
      await actions.confirmPlanning(
        session.session_id,
        untouched
          ? undefined
          : edits.flatMap((e, index) =>
              e.include ? [{ index, description: e.description.trim(), target_count: e.target }] : [],
            ),
      );
      router.push(`/week/${session.week_start}`);
      router.refresh();
    } catch (err) {
      fail(err);
      setBusy(null);
    }
  };

  const discard = async () => {
    setBusy("cancel");
    try {
      await actions.cancelPlanning(session.session_id);
    } catch {
      // Already gone is fine: discarding is the goal either way.
    }
    router.replace("/planning");
    router.refresh();
  };

  if (lost) return <DraftLost what="planning conversation" restartHref="/planning" />;

  const kept = edits.filter((e) => e.include);
  const hasPlan = kept.length > 0 && kept.every((e) => e.description.trim());

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">
            Planning week of {formatDate(session.week_start)}
          </h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400">
            One model call per message. Nothing is saved until you confirm.
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
          </CardHeader>
          <CardBody className="space-y-4">
            <ChatLog
              messages={session.messages}
              pending={busy === "turn" ? "Thinking about your week…" : null}
              empty="Say what you want out of the week — focus areas, things to leave out, how many gym sessions."
            />
            <ChatInput
              onSend={send}
              onCancel={() => controller.current?.abort()}
              busy={busy === "turn"}
              disabled={!modelReady || busy === "confirm"}
              placeholder={
                modelReady ? "e.g. Mostly the website, gym three times, skip admin" : "No provider key configured"
              }
            />
            <ErrorText>{error}</ErrorText>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Proposed plan</CardTitle>
            {session.proposal ? (
              <span className="text-xs text-neutral-500 dark:text-neutral-400">
                {session.proposal.goals.length} goal(s)
              </span>
            ) : null}
          </CardHeader>
          <CardBody className="space-y-4">
            {session.proposal ? (
              <ProposalView
                proposal={session.proposal}
                edits={edits}
                onEdit={(i, e) => setEdits((all) => all.map((old, j) => (j === i ? e : old)))}
                disabled={busy !== null}
              />
            ) : (
              <p className="text-sm text-neutral-500 dark:text-neutral-400">
                The plan appears here after your first message.
              </p>
            )}
            <Warnings warnings={session.warnings} />
            <Button variant="primary" onClick={confirm} disabled={!hasPlan || busy !== null}>
              {busy === "confirm"
                ? "Saving goals…"
                : kept.length === edits.length
                  ? "Confirm plan"
                  : `Confirm ${kept.length} of ${edits.length} goals`}
            </Button>
          </CardBody>
        </Card>
      </div>

      <details>
        <summary className="cursor-pointer text-sm text-neutral-500 dark:text-neutral-400">
          What the model sees ({session.context.backlog.length} backlog tasks,{" "}
          {session.context.projects.length} projects, {session.context.habits.length} habits)
        </summary>
        <pre className="mt-2 overflow-x-auto rounded-lg bg-neutral-100 p-4 text-xs leading-relaxed whitespace-pre-wrap text-neutral-700 dark:bg-neutral-900 dark:text-neutral-300">
          {session.context.rendered}
        </pre>
      </details>
    </div>
  );
}

/** Opens a session for the chosen week and puts its id in the URL, so a
 * reload returns to the same conversation. */
export function StartPlanning({
  weekStart,
  modelReady,
}: {
  weekStart: string;
  modelReady: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const session = await actions.startPlanning(weekStart);
      router.replace(`/planning?session=${session.session_id}`);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2">
      <Button variant="primary" onClick={start} disabled={busy || !modelReady}>
        {busy ? "Opening…" : `Plan the week of ${formatDate(weekStart)}`}
      </Button>
      {!modelReady ? (
        <p className="text-xs text-amber-700 dark:text-amber-400">
          No provider key configured, so planning is unavailable.
        </p>
      ) : null}
      <ErrorText>{error}</ErrorText>
    </div>
  );
}
