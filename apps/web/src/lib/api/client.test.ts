import { describe, expect, it, vi } from "vitest";

import { ApiError, createApiClient } from "./client";

function jsonResponse(body: unknown, init: ResponseInit & { problem?: boolean } = {}): Response {
  const { problem, ...rest } = init;
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": problem ? "application/problem+json" : "application/json" },
    ...rest,
  });
}

function setup(response: Response | (() => Response | Promise<Response>)) {
  const fetchMock = vi.fn(async (...args: [string, RequestInit?]) => {
    void args;
    return typeof response === "function" ? response() : response;
  });
  const client = createApiClient({
    baseUrl: "https://api.example.test/",
    fetchImpl: fetchMock as unknown as typeof fetch,
  });
  return { client, fetchMock };
}

describe("api client requests", () => {
  it("sends credentials and the CSRF header, and builds URLs under /api/v1", async () => {
    const { client, fetchMock } = setup(jsonResponse({ ok: true }));

    await client.post("/auth/login", { email: "a@b.co" });

    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("https://api.example.test/api/v1/auth/login");
    expect(init?.credentials).toBe("include");
    const headers = new Headers(init?.headers);
    expect(headers.get("X-Requested-With")).toBe("platform");
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(init?.body).toBe(JSON.stringify({ email: "a@b.co" }));
    expect(init?.cache).toBe("no-store");
  });

  it("sends the CSRF header on GETs too but no body or content type", async () => {
    const { client, fetchMock } = setup(jsonResponse({}));

    await client.get("/me");

    const init = fetchMock.mock.calls[0]![1]!;
    expect(new Headers(init.headers).get("X-Requested-With")).toBe("platform");
    expect(new Headers(init.headers).has("Content-Type")).toBe(false);
    expect(init.body).toBeUndefined();
  });

  it("returns undefined for 204 responses", async () => {
    const { client } = setup(new Response(null, { status: 204 }));

    await expect(client.delete("/me/sessions")).resolves.toBeUndefined();
  });

  it("never sends a client-chosen org id outside the URL path", async () => {
    const { client, fetchMock } = setup(jsonResponse({}));

    await client.get("/orgs/abc/members");

    const headers = new Headers(fetchMock.mock.calls[0]![1]!.headers);
    expect([...headers.keys()].some((name) => name.toLowerCase().includes("org"))).toBe(false);
  });
});

describe("api client errors", () => {
  it("maps RFC 9457 problem responses to ApiError", async () => {
    const { client } = setup(
      jsonResponse(
        {
          code: "validation_error",
          title: "Request validation failed",
          status: 422,
          request_id: "req-1",
          errors: [{ field: "password", code: "weak_password", message: "Too common" }],
        },
        { status: 422, problem: true },
      ),
    );

    const error = await client.post("/auth/signup", {}).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    const apiError = error as ApiError;
    expect(apiError.status).toBe(422);
    expect(apiError.code).toBe("validation_error");
    expect(apiError.requestId).toBe("req-1");
    expect(apiError.fieldErrors).toEqual({ password: "Too common" });
  });

  it("exposes Retry-After on 429", async () => {
    const { client } = setup(
      jsonResponse(
        { code: "rate_limited", title: "Too many requests", status: 429 },
        {
          status: 429,
          problem: true,
          headers: { "Retry-After": "90", "content-type": "application/problem+json" },
        },
      ),
    );

    const error = (await client.post("/auth/login", {}).catch((e: unknown) => e)) as ApiError;

    expect(error.status).toBe(429);
    expect(error.retryAfterSeconds).toBe(90);
  });

  it("survives non-JSON error bodies (proxy errors)", async () => {
    const { client } = setup(new Response("<html>Bad gateway</html>", { status: 502 }));

    const error = (await client.get("/me").catch((e: unknown) => e)) as ApiError;

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(502);
    expect(error.code).toBe("http_error");
    expect(error.message).not.toContain("<html>");
  });

  it("maps network failures to a status-0 ApiError", async () => {
    const { client } = setup(() => {
      throw new TypeError("Failed to fetch");
    });

    const error = (await client.get("/me").catch((e: unknown) => e)) as ApiError;

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(0);
    expect(error.code).toBe("network_error");
  });

  it("reports isUnauthenticated for 401 responses", async () => {
    const { client } = setup(
      jsonResponse(
        { code: "unauthenticated", title: "Authentication required" },
        { status: 401, problem: true },
      ),
    );

    const error = (await client.get("/me").catch((e: unknown) => e)) as ApiError;

    expect(error.isUnauthenticated).toBe(true);
  });
});
