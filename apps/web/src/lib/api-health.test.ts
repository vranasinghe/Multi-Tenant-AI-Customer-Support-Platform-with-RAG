import { describe, expect, it, vi } from "vitest";

import { checkApiReadiness } from "./api-health";

const readyBody = {
  status: "ok",
  service: "api",
  version: "0.1.0",
  environment: "test",
  checks: { database: { status: "ok", latency_ms: 1.2, detail: "pgvector 0.8.7" } },
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("checkApiReadiness", () => {
  it("reports ok and forwards the request id to the API", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(readyBody));

    const result = await checkApiReadiness({
      baseUrl: "http://api:8000",
      requestId: "req-12345678",
      fetchImpl,
    });

    expect(result.status).toBe("ok");
    expect(result.http_status).toBe(200);
    expect(result.checks).toEqual(readyBody.checks);

    const [url, init] = fetchImpl.mock.calls[0]!;
    expect(String(url)).toBe("http://api:8000/readyz");
    expect((init?.headers as Record<string, string>)["x-request-id"]).toBe("req-12345678");
  });

  it("reports degraded when the API answers 503", async () => {
    const fetchImpl = vi
      .fn<typeof fetch>()
      .mockResolvedValue(jsonResponse({ ...readyBody, status: "degraded" }, 503));

    const result = await checkApiReadiness({
      baseUrl: "http://api:8000",
      requestId: "r-12345678",
      fetchImpl,
    });

    expect(result.status).toBe("degraded");
    expect(result.http_status).toBe(503);
  });

  it("reports degraded when the body is not JSON", async () => {
    const fetchImpl = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response("oops", { status: 502 }));

    const result = await checkApiReadiness({
      baseUrl: "http://api:8000",
      requestId: "r-12345678",
      fetchImpl,
    });

    expect(result).toMatchObject({ status: "degraded", http_status: 502, checks: null });
  });

  it("reports unreachable on network errors instead of throwing", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockRejectedValue(new TypeError("fetch failed"));

    const result = await checkApiReadiness({
      baseUrl: "http://api:8000",
      requestId: "r-12345678",
      fetchImpl,
    });

    expect(result).toMatchObject({ status: "unreachable", http_status: null, checks: null });
  });

  it("gives up after the timeout", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockImplementation(
      (_url, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => reject(init.signal?.reason));
        }),
    );

    const result = await checkApiReadiness({
      baseUrl: "http://api:8000",
      requestId: "r-12345678",
      timeoutMs: 20,
      fetchImpl,
    });

    expect(result.status).toBe("unreachable");
  });
});
