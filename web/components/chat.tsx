"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/field";
import { cn } from "@/lib/cn";
import type { ChatMessage } from "@/lib/types";

/** The conversation so far, newest at the bottom, kept scrolled to it. */
export function ChatLog({
  messages,
  pending,
  empty,
}: {
  messages: ChatMessage[];
  pending?: React.ReactNode;
  empty: string;
}) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest" });
  }, [messages.length, pending]);

  return (
    <div className="max-h-[28rem] space-y-3 overflow-y-auto pr-1">
      {messages.length === 0 && !pending ? (
        <p className="text-sm text-neutral-500 dark:text-neutral-400">{empty}</p>
      ) : null}
      {messages.map((m, i) => (
        <div key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
          <p
            className={cn(
              "max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap",
              m.role === "user"
                ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                : "bg-neutral-100 text-neutral-800 dark:bg-neutral-800 dark:text-neutral-200",
            )}
          >
            {m.text}
          </p>
        </div>
      ))}
      {pending ? (
        <div className="flex justify-start">
          <div className="rounded-lg bg-neutral-100 px-3 py-2 text-sm text-neutral-500 dark:bg-neutral-800 dark:text-neutral-400">
            {pending}
          </div>
        </div>
      ) : null}
      <div ref={end} />
    </div>
  );
}

/** Message box with send, and cancel while a turn is running (NFR-1).
 * Enter sends; Shift+Enter is a newline. */
export function ChatInput({
  onSend,
  onCancel,
  busy,
  disabled,
  placeholder,
}: {
  onSend: (text: string) => Promise<boolean>;
  onCancel: () => void;
  busy: boolean;
  disabled?: boolean;
  placeholder: string;
}) {
  const [text, setText] = useState("");

  const send = async () => {
    const value = text.trim();
    if (!value || busy || disabled) return;
    // Keep the text until the turn succeeds, so a failure can be retried.
    if (await onSend(value)) setText("");
  };

  return (
    <div className="space-y-2">
      <Textarea
        rows={2}
        value={text}
        disabled={busy || disabled}
        placeholder={placeholder}
        aria-label="Message"
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            send();
          }
        }}
      />
      <div className="flex gap-2">
        <Button variant="primary" onClick={send} disabled={busy || disabled || !text.trim()}>
          Send
        </Button>
        {busy ? (
          <Button variant="ghost" onClick={onCancel}>
            Stop waiting
          </Button>
        ) : null}
      </div>
    </div>
  );
}
