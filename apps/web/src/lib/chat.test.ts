import { describe, expect, it, vi } from "vitest";
import { readChatStream, safeCitationUrl } from "./chat";

function stream(text: string, split = false) {
  const bytes = new TextEncoder().encode(text);
  return new Response(
    new ReadableStream({
      start(controller) {
        if (split) for (const byte of bytes) controller.enqueue(Uint8Array.of(byte));
        else controller.enqueue(bytes);
        controller.close();
      },
    }),
    { headers: { "content-type": "text/event-stream" } },
  );
}

describe("chat transport", () => {
  it("parses UTF-8 characters and CRLF split across bytes", async () => {
    const event = vi.fn();
    await readChatStream(
      stream(
        'event: delta\r\ndata: {"text":"සිංහල"}\r\n\r\nevent: done\r\ndata: {"status":"complete"}\r\n\r\n',
        true,
      ),
      event,
    );
    expect(event.mock.calls[0]?.[0]).toEqual({ event: "delta", data: { text: "සිංහල" } });
    expect(event).toHaveBeenCalledTimes(2);
  });

  it("detects an interrupted stream instead of accepting partial output", async () => {
    await expect(
      readChatStream(stream('event: delta\ndata: {"text":"partial"}\n\n'), vi.fn()),
    ).rejects.toThrow("before the answer finished");
  });

  it("preserves actionable pre-stream HTTP errors", async () => {
    await expect(
      readChatStream(
        new Response(JSON.stringify({ code: "quota_exceeded", detail: "Monthly limit reached" }), {
          status: 429,
          headers: { "content-type": "application/problem+json" },
        }),
        vi.fn(),
      ),
    ).rejects.toMatchObject({ status: 429, code: "quota_exceeded" });
  });

  it("rejects oversized frames and non-SSE responses", async () => {
    await expect(readChatStream(stream("x".repeat(260_000)), vi.fn())).rejects.toThrow("too large");
    await expect(readChatStream(new Response("ok"), vi.fn())).rejects.toThrow("chat stream");
  });

  it("never links unsafe document URIs", () => {
    for (const uri of [
      "javascript:alert(1)",
      "data:text/html,test",
      "s3://private/file",
      "https://user:pass@evil.test/",
    ])
      expect(safeCitationUrl(uri)).toBeUndefined();
    expect(safeCitationUrl("https://help.test/returns")).toBe("https://help.test/returns");
  });
});
