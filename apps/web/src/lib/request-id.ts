import { REQUEST_ID_HEADER, REQUEST_ID_PATTERN } from "@acs/shared-types";

export { REQUEST_ID_HEADER };

/** Accept a client-supplied request id only if it is well-formed; otherwise mint a new one. */
export function resolveRequestId(incoming: string | null | undefined): string {
  if (incoming && REQUEST_ID_PATTERN.test(incoming)) return incoming;
  return crypto.randomUUID();
}
