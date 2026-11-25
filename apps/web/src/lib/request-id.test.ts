import { describe, expect, it } from "vitest";

import { resolveRequestId } from "./request-id";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe("resolveRequestId", () => {
  it("keeps a well-formed incoming id", () => {
    expect(resolveRequestId("req_abc.123-XYZ")).toBe("req_abc.123-XYZ");
  });

  it("generates a UUID when none is supplied", () => {
    expect(resolveRequestId(null)).toMatch(UUID);
    expect(resolveRequestId(undefined)).toMatch(UUID);
  });

  it.each([
    ["header injection", "abcdefgh\r\nSet-Cookie: x=1"],
    ["too short", "abc"],
    ["too long", "a".repeat(129)],
    ["disallowed characters", "<script>alert(1)</script>"],
  ])("replaces a malformed id (%s)", (_label, value) => {
    const id = resolveRequestId(value);
    expect(id).not.toBe(value);
    expect(id).toMatch(UUID);
  });
});
