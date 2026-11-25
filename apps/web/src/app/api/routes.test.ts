import { beforeEach, describe, expect, it, vi } from "vitest";

const okBody = { status: "ok", service: "api", version: "0.1.0", environment: "test", checks: {} };

describe("web health routes", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubEnv("API_INTERNAL_URL", "http://api.test:8000");
  });

  it("GET /api/health is always ok and echoes a valid request id", async () => {
    const { GET } = await import("./health/route");

    const response = GET(
      new Request("http://web.test/api/health", { headers: { "x-request-id": "req-abcdefgh" } }),
    );

    expect(response.status).toBe(200);
    expect(response.headers.get("x-request-id")).toBe("req-abcdefgh");
    await expect(response.json()).resolves.toMatchObject({ status: "ok", service: "web" });
  });

  it("GET /api/ready returns 200 when the API is ready", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response(JSON.stringify(okBody), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const { GET } = await import("./ready/route");

    const response = await GET(new Request("http://web.test/api/ready"));

    expect(response.status).toBe(200);
    const body = (await response.json()) as { status: string; api: { status: string } };
    expect(body).toMatchObject({ status: "ok", service: "web", api: { status: "ok" } });
    expect(String(fetchMock.mock.calls[0]![0])).toBe("http://api.test:8000/readyz");
    // The id minted by the web app is the one forwarded to the API.
    const forwarded = (fetchMock.mock.calls[0]![1]?.headers as Record<string, string>)[
      "x-request-id"
    ];
    expect(response.headers.get("x-request-id")).toBe(forwarded);
  });

  it("GET /api/ready returns 503 when the API is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockRejectedValue(new TypeError("fetch failed")));
    vi.spyOn(process.stderr, "write").mockReturnValue(true);
    const { GET } = await import("./ready/route");

    const response = await GET(new Request("http://web.test/api/ready"));

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toMatchObject({
      status: "degraded",
      api: { status: "unreachable" },
    });
  });
});
