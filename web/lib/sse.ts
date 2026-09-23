import { ApiError, send } from "./api";
import type { ApiErrorType, DecompositionSession, TurnProgress } from "./types";

/** Split an SSE byte stream into (event, data) pairs. */
async function* readEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<[string, string]> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      let boundary: number;
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        let event = "message";
        const data: string[] = [];
        for (const line of block.split("\n")) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
        }
        if (data.length) yield [event, data.join("\n")];
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/**
 * Run one decomposition turn (POST .../messages), reporting progress as it
 * streams and resolving to the whole session once the turn completes.
 *
 * EventSource can't POST, so this reads the stream from fetch. Aborting the
 * signal closes the connection, which is also how the server learns to stop
 * the turn before its next model call.
 */
export async function streamDecompositionTurn(
  sessionId: string,
  text: string,
  {
    onProgress,
    signal,
    exclude,
  }: {
    onProgress: (p: TurnProgress) => void;
    signal?: AbortSignal;
    /** Unticked new items, dropped from the draft before the model sees it. */
    exclude?: { milestone_refs: string[]; task_refs: string[] };
  },
): Promise<DecompositionSession> {
  // A missing session or provider key fails before streaming, as a normal
  // JSON error; `send` turns those into ApiErrors.
  const response = await send("POST", `/api/decomposition/sessions/${sessionId}/messages`, {
    body: {
      text,
      exclude_milestone_refs: exclude?.milestone_refs ?? [],
      exclude_task_refs: exclude?.task_refs ?? [],
    },
    signal,
  });
  if (!response.body) throw new ApiError("internal", "The server sent no stream.", response.status);

  for await (const [event, data] of readEvents(response.body)) {
    const payload = JSON.parse(data);
    if (event === "progress") onProgress(payload as TurnProgress);
    else if (event === "result") return payload as DecompositionSession;
    else if (event === "error") {
      const { type, message } = payload as { type: ApiErrorType; message: string };
      throw new ApiError(type, message, response.status);
    }
  }
  throw new ApiError("internal", "The turn ended without a result. Try again.", response.status);
}
