/** Organization helpers. Everything here is presentation: the server authorizes every request. */

const STORAGE_KEY = "acs.activeOrg";

export interface OrgRef {
  id: string;
}

/**
 * Which org the UI should treat as active. The org in the URL wins, then the remembered one,
 * then the first. Every candidate must be one of the memberships the *server* returned, so a
 * stale or tampered localStorage value can never point the UI at a foreign org.
 */
export function resolveActiveOrgId(
  memberships: readonly OrgRef[],
  hints: { routeOrgId?: string | null; storedOrgId?: string | null },
): string | null {
  const ids = new Set(memberships.map((org) => org.id));
  for (const candidate of [hints.routeOrgId, hints.storedOrgId]) {
    if (candidate && ids.has(candidate)) return candidate;
  }
  return memberships[0]?.id ?? null;
}

export function can(org: { permissions: readonly string[] } | null, permission: string): boolean {
  return org?.permissions.includes(permission) ?? false;
}

export function readStoredOrgId(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null; // storage blocked (private mode, disabled cookies)
  }
}

export function storeOrgId(orgId: string): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, orgId);
  } catch {
    // Remembering the last org is a convenience; ignore storage failures.
  }
}
