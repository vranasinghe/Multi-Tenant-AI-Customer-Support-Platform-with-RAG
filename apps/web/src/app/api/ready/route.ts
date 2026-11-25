import type { WebReadinessResponse } from "@acs/shared-types";

import { serverEnv } from "@/env";
import { checkApiReadiness } from "@/lib/api-health";
import { logger } from "@/lib/logger";
import { REQUEST_ID_HEADER, resolveRequestId } from "@/lib/request-id";

export const dynamic = "force-dynamic";

/**
 * Readiness: the web server can reach a ready API. Returns 503 otherwise so orchestrators
 * and the smoke test can detect broken wiring between containers.
 */
export async function GET(request: Request): Promise<Response> {
  const requestId = resolveRequestId(request.headers.get(REQUEST_ID_HEADER));
  const api = await checkApiReadiness({ baseUrl: serverEnv().API_INTERNAL_URL, requestId });
  const ready = api.status === "ok";

  if (!ready) {
    logger.warn("web.readiness.degraded", {
      request_id: requestId,
      api_status: api.status,
      http_status: api.http_status,
    });
  }

  const body: WebReadinessResponse = { status: ready ? "ok" : "degraded", service: "web", api };
  return Response.json(body, {
    status: ready ? 200 : 503,
    headers: { [REQUEST_ID_HEADER]: requestId, "cache-control": "no-store" },
  });
}
