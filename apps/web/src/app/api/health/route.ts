import type { LivenessResponse } from "@acs/shared-types";

import { REQUEST_ID_HEADER, resolveRequestId } from "@/lib/request-id";

export const dynamic = "force-dynamic";

/** Liveness: the Next.js server is up. Deliberately checks no dependencies. */
export function GET(request: Request): Response {
  const requestId = resolveRequestId(request.headers.get(REQUEST_ID_HEADER));
  const body: LivenessResponse = {
    status: "ok",
    service: "web",
    version: process.env.APP_VERSION ?? "0.1.0",
  };
  return Response.json(body, {
    headers: { [REQUEST_ID_HEADER]: requestId, "cache-control": "no-store" },
  });
}
