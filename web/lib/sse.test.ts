import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api";
import { streamDecompositionTurn } from "@/lib/sse";

function streamOf(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c));
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

const session = { session_id: "s1", draft: {}, messages: [], last_turn: { steps: 2, tool_calls: 1, hit_limit: false } };

afterEach(() => vi.unstubAllGlobals());

describe("streamDecompositionTurn (NFR-2)", () => {
  it("reports progress in order and resolves to the result, across split chunks", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      streamOf([
        'event: progress\ndata: {"phase":"step","step":1,"tool_calls":0,"tool":null}\n\n',
        'event: progress\ndata: {"phase":"tool","step":1,"tool_calls":1,',
        '"tool":"add_milestone"}\n\nevent: result\n',
        `data: ${JSON.stringify(session)}\n\n`,
      ]),
    );
    vi.stubGlobal("fetch", fetchMock);
    const progress: unknown[] = [];

    const result = await streamDecompositionTurn("s1", "break it down", { onProgress: (p) => progress.push(p) });

    expect(result).toEqual(session);
    expect(progress).toEqual([
      { phase: "step", step: 1, tool_calls: 0, tool: null },
      { phase: "tool", step: 1, tool_calls: 1, tool: "add_milestone" },
    ]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/api\/decomposition\/sessions\/s1\/messages$/);
    expect(JSON.parse(init.body)).toEqual({
      text: "break it down",
      exclude_milestone_refs: [],
      exclude_task_refs: [],
    });
  });

  it("turns an in-band error event into a typed ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        streamOf(['event: error\ndata: {"type":"provider","message":"The model call failed (Timeout)"}\n\n']),
      ),
    );

    const error = await streamDecompositionTurn("s1", "x", { onProgress: () => {} }).catch((e) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.type).toBe("provider");
    expect(error.message).toContain("Timeout");
  });

  it("a lost session fails before streaming with session_expired", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: { type: "session_expired", message: "Start again." } }), {
          status: 404,
        }),
      ),
    );

    const error = await streamDecompositionTurn("gone", "x", { onProgress: () => {} }).catch((e) => e);

    expect(error.type).toBe("session_expired");
    expect(error.status).toBe(404);
  });

  it("a stream that ends without a result is an error, not a hang", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(streamOf(["event: progress\ndata: {}\n\n"])));
    await expect(streamDecompositionTurn("s1", "x", { onProgress: () => {} })).rejects.toThrow(/without a result/);
  });
});
