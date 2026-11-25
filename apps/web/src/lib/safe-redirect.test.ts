import { describe, expect, it } from "vitest";

import { safeRedirectPath } from "./safe-redirect";

describe("safeRedirectPath", () => {
  it.each([
    ["/dashboard", "/dashboard"],
    ["/orgs/0193-abc/members", "/orgs/0193-abc/members"],
    ["/account", "/account"],
    ["/invite?token=abc_DEF-123", "/invite?token=abc_DEF-123"],
  ])("allows in-app path %s", (input, expected) => {
    expect(safeRedirectPath(input)).toBe(expected);
  });

  it.each([
    "https://evil.example/phish",
    "//evil.example",
    "/\\evil.example",
    "\\\\evil.example",
    "javascript:alert(1)",
    "/%2F%2Fevil.example",
    "/%5Cevil.example",
    "/dashboard\r\nSet-Cookie: x=1",
    "/unknown-area",
    "dashboard",
    "",
    "   ",
    "/dashboard/../../etc/passwd",
  ])("rejects %j", (input) => {
    expect(safeRedirectPath(input)).toBe("/dashboard");
  });

  it("falls back for null and undefined", () => {
    expect(safeRedirectPath(null)).toBe("/dashboard");
    expect(safeRedirectPath(undefined)).toBe("/dashboard");
  });

  it("honours a custom fallback", () => {
    expect(safeRedirectPath("https://evil.example", "/account")).toBe("/account");
  });
});
