/**
 * Browser → API client (ADR-021: the dashboard talks to FastAPI directly with the session cookie).
 *
 * - `credentials: "include"` sends the HttpOnly `__Host-session` cookie; JS never sees it.
 * - Every request carries `X-Requested-With: platform`, which the API requires on state-changing
 *   requests as a CSRF defence (docs/SECURITY.md §3).
 * - Org ids only ever appear in URL paths; the server re-verifies membership on each request.
 */

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fieldErrors: Record<string, string>;
  readonly requestId?: string;
  readonly retryAfterSeconds?: number;

  constructor(init: {
    status: number;
    code: string;
    message: string;
    fieldErrors?: Record<string, string>;
    requestId?: string;
    retryAfterSeconds?: number;
  }) {
    super(init.message);
    this.name = "ApiError";
    this.status = init.status;
    this.code = init.code;
    this.fieldErrors = init.fieldErrors ?? {};
    this.requestId = init.requestId;
    this.retryAfterSeconds = init.retryAfterSeconds;
  }

  get isUnauthenticated(): boolean {
    return this.status === 401;
  }
}

interface ProblemBody {
  code?: unknown;
  title?: unknown;
  detail?: unknown;
  request_id?: unknown;
  errors?: unknown;
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function parseFieldErrors(errors: unknown): Record<string, string> {
  const result: Record<string, string> = {};
  if (!Array.isArray(errors)) return result;
  for (const entry of errors) {
    if (typeof entry !== "object" || entry === null) continue;
    const { field, message } = entry as { field?: unknown; message?: unknown };
    const key = asString(field);
    const text = asString(message);
    if (key && text && !(key in result)) result[key] = text;
  }
  return result;
}

export async function toApiError(response: Response): Promise<ApiError> {
  let problem: ProblemBody = {};
  if ((response.headers.get("content-type") ?? "").includes("json")) {
    try {
      problem = (await response.json()) as ProblemBody;
    } catch {
      problem = {};
    }
  }
  const retryAfter = Number.parseInt(response.headers.get("retry-after") ?? "", 10);
  return new ApiError({
    status: response.status,
    code: asString(problem.code) ?? "http_error",
    message:
      asString(problem.detail) ?? asString(problem.title) ?? `Request failed (${response.status})`,
    fieldErrors: parseFieldErrors(problem.errors),
    requestId: asString(problem.request_id),
    retryAfterSeconds: Number.isFinite(retryAfter) ? retryAfter : undefined,
  });
}

export interface ApiClientOptions {
  baseUrl: string;
  fetchImpl?: typeof fetch;
}

export interface ApiClient {
  get<T>(path: string): Promise<T>;
  post<T>(path: string, body?: unknown): Promise<T>;
  /** Raw-body upload (a file's bytes as the request body, not multipart). */
  upload<T>(path: string, file: Blob, contentType: string): Promise<T>;
  patch<T>(path: string, body: unknown): Promise<T>;
  put<T>(path: string, body: unknown): Promise<T>;
  delete<T = void>(path: string): Promise<T>;
  download(path: string): Promise<Blob>;
}

export function createApiClient({ baseUrl, fetchImpl }: ApiClientOptions): ApiClient {
  const root = `${baseUrl.replace(/\/+$/, "")}/api/v1`;

  async function request<T>(
    method: string,
    path: string,
    body?: unknown,
    raw?: { blob: Blob; contentType: string },
  ): Promise<T> {
    const headers: Record<string, string> = {
      Accept: "application/json",
      "X-Requested-With": "platform",
    };
    const init: RequestInit = {
      method,
      headers,
      credentials: "include",
      cache: "no-store",
    };
    if (raw) {
      headers["Content-Type"] = raw.contentType;
      init.body = raw.blob;
    } else if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }

    let response: Response;
    try {
      response = await (fetchImpl ?? fetch)(`${root}${path}`, init);
    } catch {
      throw new ApiError({
        status: 0,
        code: "network_error",
        message: "Can't reach the server. Check your connection and try again.",
      });
    }
    if (!response.ok) throw await toApiError(response);
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  async function download(path: string): Promise<Blob> {
    const headers: Record<string, string> = {
      Accept: "text/csv, application/json",
      "X-Requested-With": "platform",
    };
    let response: Response;
    try {
      response = await (fetchImpl ?? fetch)(`${root}${path}`, {
        method: "GET",
        headers,
        credentials: "include",
        cache: "no-store",
      });
    } catch {
      throw new ApiError({
        status: 0,
        code: "network_error",
        message: "Can't reach the server. Check your connection and try again.",
      });
    }
    if (!response.ok) throw await toApiError(response);
    return response.blob();
  }

  return {
    get: (path) => request("GET", path),
    post: (path, body) => request("POST", path, body ?? {}),
    patch: (path, body) => request("PATCH", path, body),
    put: (path, body) => request("PUT", path, body),
    delete: (path) => request("DELETE", path),
    upload: (path, file, contentType) =>
      request("POST", path, undefined, { blob: file, contentType }),
    download,
  };
}

export function publicApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}
