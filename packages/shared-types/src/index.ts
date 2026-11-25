/**
 * Hand-written mirrors of the API health contracts (services/api/app/schemas/health.py).
 * Replaced by OpenAPI-generated types once the API surface grows (ADR-021, ADR-029).
 */

export type CheckStatus = "ok" | "error";
export type OverallStatus = "ok" | "degraded";

export interface LivenessResponse {
  status: "ok";
  service: string;
  version: string;
}

export interface DependencyCheck {
  status: CheckStatus;
  latency_ms: number;
  detail: string | null;
}

export interface ReadinessResponse {
  status: OverallStatus;
  service: string;
  version: string;
  environment: string;
  checks: Record<string, DependencyCheck>;
}

/** Shape returned by the web app's own /api/ready endpoint. */
export interface WebReadinessResponse {
  status: OverallStatus;
  service: "web";
  api: {
    status: "ok" | "degraded" | "unreachable";
    latency_ms: number;
    http_status: number | null;
    checks: Record<string, DependencyCheck> | null;
  };
}

/** Request ids accepted from clients: 8–128 chars of [A-Za-z0-9._-]. Mirrors the API rule. */
export const REQUEST_ID_PATTERN = /^[A-Za-z0-9._-]{8,128}$/;
export const REQUEST_ID_HEADER = "x-request-id";
