import { describe, expect, it } from "vitest";

import { can, resolveActiveOrgId } from "./orgs";

const orgs = [{ id: "a" }, { id: "b" }, { id: "c" }];

describe("resolveActiveOrgId", () => {
  it("prefers the org in the URL when the user belongs to it", () => {
    expect(resolveActiveOrgId(orgs, { routeOrgId: "b", storedOrgId: "c" })).toBe("b");
  });

  it("falls back to the stored preference only if the server says it is a membership", () => {
    expect(resolveActiveOrgId(orgs, { routeOrgId: "zzz", storedOrgId: "c" })).toBe("c");
    expect(resolveActiveOrgId(orgs, { storedOrgId: "someone-elses-org" })).toBe("a");
  });

  it("falls back to the first membership, and to null with none", () => {
    expect(resolveActiveOrgId(orgs, {})).toBe("a");
    expect(resolveActiveOrgId([], { routeOrgId: "a", storedOrgId: "a" })).toBeNull();
  });
});

describe("can", () => {
  it("checks the permission list the server returned", () => {
    const org = { permissions: ["org:read", "member:read"] };
    expect(can(org, "member:read")).toBe(true);
    expect(can(org, "member:manage")).toBe(false);
    expect(can(null, "org:read")).toBe(false);
  });
});
