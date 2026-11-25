/**
 * Open-redirect defence (docs/SECURITY.md §11): post-login redirects must be relative in-app
 * paths on an allowlist. Anything else (absolute URLs, protocol-relative `//host`, backslash
 * tricks, encoded slashes, control characters, path traversal) falls back to a safe default.
 */

const ALLOWED_PREFIXES = ["/dashboard", "/orgs", "/account", "/invite"] as const;
const CONTROL_CHARS = /[\u0000-\u001f\u007f]/;

export function safeRedirectPath(
  next: string | null | undefined,
  fallback: string = "/dashboard",
): string {
  if (!next) return fallback;
  const raw = next.trim();
  if (!raw.startsWith("/") || raw.startsWith("//")) return fallback;
  if (CONTROL_CHARS.test(raw) || raw.includes("\\") || raw.includes("..")) return fallback;

  let url: URL;
  try {
    url = new URL(raw, "http://internal.invalid");
  } catch {
    return fallback;
  }
  if (url.origin !== "http://internal.invalid") return fallback;

  let decodedPath: string;
  try {
    decodedPath = decodeURIComponent(url.pathname);
  } catch {
    return fallback;
  }
  if (decodedPath.startsWith("//") || decodedPath.includes("\\") || decodedPath.includes("..")) {
    return fallback;
  }

  const allowed = ALLOWED_PREFIXES.some(
    (prefix) => url.pathname === prefix || url.pathname.startsWith(`${prefix}/`),
  );
  return allowed ? `${url.pathname}${url.search}` : fallback;
}
