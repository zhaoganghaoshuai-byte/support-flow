import { afterEach, describe, expect, it, vi } from "vitest";
import { setToken, streamChat } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("SSE transport", () => {
  it("decodes Chinese text split across arbitrary byte and frame boundaries", async () => {
    const wire =
      'event: status\ndata: {"label":"正在检索"}\n\nevent: result\ndata: {"answer":"中文排查建议"}\n\nevent: done\ndata: {"run_id":"run-1"}\n\n';
    const bytes = new TextEncoder().encode(wire);
    let offset = 0;
    const read = async () => {
      if (offset >= bytes.length) return { done: true, value: undefined };
      const value = bytes.slice(offset, offset + 5);
      offset += 5;
      return { done: false, value };
    };
    const fetch = vi.fn(async () => ({
      ok: true,
      body: { getReader: () => ({ read }) },
    }));
    vi.stubGlobal("fetch", fetch);
    setToken("transport-test-token");
    const seen: [string, unknown][] = [];
    await streamChat("conversation", "问题", "request-id", (event, data) =>
      seen.push([event, data]),
    );
    expect(seen.map(([event]) => event)).toEqual(["status", "result", "done"]);
    expect(seen[1][1]).toEqual({ answer: "中文排查建议" });
    expect(fetch.mock.calls.length).toBe(1);
  });

  it("reports a disconnected stream without a terminal frame", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        body: {
          getReader: () => ({
            read: async () => ({ done: true, value: undefined }),
          }),
        },
      })),
    );
    await expect(
      streamChat("c", "问题", "request-id", () => {}),
    ).rejects.toThrow("连接中断");
  });
});
