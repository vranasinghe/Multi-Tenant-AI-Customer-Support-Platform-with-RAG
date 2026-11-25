import type { ReadinessResponse, WebReadinessResponse } from "@acs/shared-types";

import { REQUEST_ID_HEADER } from "./request-id";

export type ApiReadiness = WebReadinessResponse["api"];

interface CheckOptions {
  baseUrl: string;
  requestId: string;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

/**
 * Ask the API whether it (and its dependencies) are ready. Never throws: network failures
 * and timeouts are reported as `unreachable` so callers can render/return a status.
 */
export async function checkApiReadiness({
  baseUrl,
  requestId,
  timeoutMs = 2000,
  fetchImpl = fetch,
}: CheckOptions): Promise<ApiReadiness> {
  const started = performance.now();
  const elapsed = () => Math.round(performance.now() - started);
  const url = new URL("/readyz", baseUrl);

  try {
    const response = await fetchImpl(url, {
      headers: { [REQUEST_ID_HEADER]: requestId, accept: "application/json" },
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
    const body = (await response.json().catch(() => null)) as ReadinessResponse | null;
    return {
      status: response.ok && body?.status === "ok" ? "ok" : "degraded",
      latency_ms: elapsed(),
      http_status: response.status,
      checks: body?.checks ?? null,
    };
  } catch {
    return { status: "unreachable", latency_ms: elapsed(), http_status: null, checks: null };
  }
}
