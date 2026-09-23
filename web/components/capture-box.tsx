"use client";

import { useState } from "react";
import { RatingQueue } from "@/components/rating";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorText, Textarea } from "@/components/ui/field";
import { actions } from "@/lib/api";
import { useAction } from "@/lib/use-action";
import type { Task } from "@/lib/types";

/**
 * Backlog capture (FR-1, FR-2, FR-5). One model call turns the text into
 * tasks; they are saved unrated and queued here for rating. A failed call
 * saves nothing, so the text is kept for a retry.
 */
export function CaptureBox({ modelReady, unrated }: { modelReady: boolean; unrated: Task[] }) {
  const [text, setText] = useState("");
  const [queue, setQueue] = useState<Task[] | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const { run, cancel, busy, error } = useAction();

  const capture = async () => {
    setNotice(null);
    const created = await run((signal) => actions.capture(text, signal));
    if (!created) return;
    setText("");
    if (created.length === 0) {
      setNotice("No tasks found in that text; nothing was added.");
    } else {
      setQueue(created);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Capture</CardTitle>
        <span className="text-xs text-neutral-500 dark:text-neutral-400">
          One model call · tasks are saved unrated
        </span>
      </CardHeader>
      <CardBody className="space-y-3">
        {queue ? (
          <RatingQueue key={queue.map((t) => t.id).join(",")} tasks={queue} onEmpty={() => setQueue(null)} />
        ) : (
          <>
            <Textarea
              rows={3}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && text.trim() && !busy) capture();
              }}
              placeholder="Everything on your mind: fix the login bug, email Sam about the invoice, book the dentist…"
              disabled={busy || !modelReady}
              aria-label="Tasks to capture"
            />
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="primary" onClick={capture} disabled={busy || !text.trim() || !modelReady}>
                {busy ? "Extracting tasks…" : "Capture"}
              </Button>
              {busy ? (
                <Button variant="ghost" onClick={cancel}>
                  Cancel
                </Button>
              ) : null}
              {!modelReady ? (
                <span className="text-xs text-amber-700 dark:text-amber-400">
                  No provider key configured — capture is unavailable, everything else works.
                </span>
              ) : null}
              {unrated.length > 0 && !busy ? (
                <Button variant="ghost" className="ml-auto" onClick={() => setQueue(unrated)}>
                  Rate {unrated.length} unrated
                </Button>
              ) : null}
            </div>
            {notice ? <p className="text-sm text-neutral-600 dark:text-neutral-400">{notice}</p> : null}
            <ErrorText>{error}</ErrorText>
          </>
        )}
      </CardBody>
    </Card>
  );
}
